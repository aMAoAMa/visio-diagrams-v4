param(
 [Parameter(Mandatory=$true)][string]$ScenePath,
 [Parameter(Mandatory=$true)][string]$OutputDirectory,
 [switch]$Replace,
 [ValidateRange(96,1200)][int]$RasterDpi=300,
 [ValidateSet('AlphaSafe','Opaque')][string]$PngMode='AlphaSafe'
)
$ErrorActionPreference='Stop'
function Has($o,$key){return $null -ne $o.PSObject.Properties[$key]}
function Num($n){return ([double]$n).ToString('R',[Globalization.CultureInfo]::InvariantCulture)}
function Finite($n){return $null -ne $n -and ![double]::IsNaN([double]$n) -and ![double]::IsInfinity([double]$n)}
function Cell($s,$key,$value){$s.CellsU($key).FormulaU=[string]$value}
# Side names refer to the unrotated node in page coordinates.
$portOffsets = @{left=@(0,0.5);right=@(1,0.5);top=@(0.5,1);bottom=@(0.5,0)}
function GlueEndpoint($cell,$node,$side){
 if($side){
  $offset=$portOffsets[$side]
  $cell.GlueToPos($node,[double]$offset[0],[double]$offset[1])
 }else{
  $cell.GlueTo($node.CellsU('PinX'))
 }
}
function Color($hex){
 if($hex -notmatch '^#[0-9a-fA-F]{6}$'){throw "Invalid color: $hex"}
 return 'RGB({0},{1},{2})' -f [Convert]::ToInt32($hex.Substring(1,2),16),[Convert]::ToInt32($hex.Substring(3,2),16),[Convert]::ToInt32($hex.Substring(5,2),16)
}
function FontId($document,$name){
 $aliases=@{'Microsoft YaHei'='微软雅黑';'SimSun'='宋体';'SimHei'='黑体';'Microsoft JhengHei'='微軟正黑體'}
 $candidates=@($name)
 if($aliases.ContainsKey($name)){$candidates+=@($aliases[$name])}
 foreach($candidate in $candidates){try{return $document.Fonts.Item($candidate).ID}catch{}}
 throw "Requested font is not available in Visio: $name"
}
function ApplyStyle($shape,$item){
 Cell $shape 'LinePattern' '1'
 Cell $shape 'BeginArrow' '0';Cell $shape 'EndArrow' '0'
 Cell $shape 'ShdwPattern' '0'
 if($item.noLine){Cell $shape 'LinePattern' '0'}
 elseif($item.line){Cell $shape 'LineColor' (Color $item.line);Cell $shape 'LineWeight' ((Num $(if(Has $item 'weight'){$item.weight}else{1}))+' pt')}
 elseif($item.kind -eq 'text'){Cell $shape 'LinePattern' '0'}
 if($item.fill){Cell $shape 'FillForegnd' (Color $item.fill);Cell $shape 'FillPattern' '1'}else{Cell $shape 'FillPattern' '0'}
 if(Has $item 'alpha'){Cell $shape 'FillForegndTrans' ((Num $item.alpha)+'%')}
 if($item.dash -and !$item.noLine){Cell $shape 'LinePattern' '2'}
 if($item.endArrow){Cell $shape 'EndArrow' '4';Cell $shape 'EndArrowSize' '2'}
 if($item.startArrow){Cell $shape 'BeginArrow' '4';Cell $shape 'BeginArrowSize' '2'}
 if($item.kind -eq 'rect' -and (Has $item 'round')){Cell $shape 'Rounding' ((Num $item.round)+' in')}
}
function ApplyText($shape,$item,$document,$defaultFont,$defaultEastAsiaFont){
 if(!(Has $item 'text')){return}
 $plain=[string]$item.text;$runs=@()
 if($item.notation){
  $plain='';$cursor=0
  foreach($m in [regex]::Matches([string]$item.text,'([_^])\{([^}]+)\}')){
   $plain+=([string]$item.text).Substring($cursor,$m.Index-$cursor)
   $begin=$plain.Length;$plain+=$m.Groups[2].Value
   $runs+=@{start=$begin;end=$plain.Length;position=$(if($m.Groups[1].Value -eq '_'){'subscript'}else{'superscript'})}
   $cursor=$m.Index+$m.Length
  }
  $plain+=([string]$item.text).Substring($cursor)
 }elseif($item.runs){$runs=@($item.runs)}
 $shape.Text=$plain
 $font=if($item.font){$item.font}else{$defaultFont}
 $size=if($item.size){[double]$item.size}else{18.0}
 Cell $shape 'Char.Font' (FontId $document $font)
 $eaFont=if($item.fontEastAsia){$item.fontEastAsia}else{$defaultEastAsiaFont}
 Cell $shape 'Char.AsianFont' (FontId $document $eaFont)
 Cell $shape 'Char.Size' ((Num $size)+' pt')
 if(Has $item 'italic'){Cell $shape 'Char.Style' $(if($item.italic){2}else{0})}
 Cell $shape 'Char.Color' (Color $(if($item.color){$item.color}else{'#20384A'}))
 Cell $shape 'Para.HorzAlign' $(if(Has $item 'align'){$item.align}else{1})
 Cell $shape 'VerticalAlign' '1'
 foreach($key in @('LeftMargin','RightMargin','TopMargin','BottomMargin')){Cell $shape $key '0.02 in'}
 foreach($run in $runs){
  if($run.start -lt 0 -or $run.end -gt $plain.Length -or $run.end -le $run.start){throw 'Invalid native text run range'}
  if($run.position -notin @('subscript','superscript')){throw 'Invalid text position'}
  $chars=$shape.Characters;$chars.Begin=[int]$run.start;$chars.End=[int]$run.end
  $chars.CharProps(4)=$(if($run.position -eq 'subscript'){2}else{1})
  $chars.CharProps(7)=$size*.72
 }
}
function AuditShapes($collection,$records){
 foreach($s in $collection){
  $record=[pscustomobject]@{id=$s.ID;sourceId=[string]$s.Data2;kind=$s.Type;layer=$s.CellsU('LayerMember').FormulaU;text=[string]$s.Text;semantic=[string]$s.Data1}
  $records.Add($record)
  if($s.Type -eq 2){AuditShapes $s.Shapes $records}
 }
}

$source=[IO.Path]::GetFullPath($ScenePath)
$out=[IO.Path]::GetFullPath($OutputDirectory)
$payload=Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
$scenes=@($payload.scenes)
if($scenes.Count -eq 0 -or $null -eq $scenes[0]){throw 'Expected nonempty scenes array'}
$sceneNames=@{}
# Validate all scene data before starting the native app or changing outputs.
foreach($scene in $scenes){
 if(!$scene.name -or $scene.name -match '[\\/:*?"<>|]' -or $scene.name -in @('.','..') -or $scene.name.EndsWith('.') -or $scene.name.EndsWith(' ')){throw 'Unsafe scene basename'}
 if($sceneNames.ContainsKey($scene.name)){throw 'Duplicate scene name'};$sceneNames[$scene.name]=$true
 if(!(Finite $scene.width) -or !(Finite $scene.height) -or $scene.width -le 0 -or $scene.height -le 0){throw 'Invalid page dimensions'}
 $layers=@{};$semantics=@{};$ids=@{}
 foreach($layer in $scene.layers){
  if(!$layer.name -or !$layer.owner -or !$layer.concept -or $layers.ContainsKey($layer.name)){throw 'Invalid/duplicate layer declaration'}
  $key=[string]$layer.owner+[char]0x1f+[string]$layer.concept
  if($semantics.ContainsKey($key)){throw "One owner/concept split into layers: $($layer.owner), $($layer.concept)"}
  $semantics[$key]=$true;$layers[$layer.name]=$layer
 }
 if(@($scene.shapes).Count -eq 0){throw 'Empty diagram'}
 foreach($item in $scene.shapes){
  if(!$item.id -or $ids.ContainsKey($item.id)){throw 'Missing/duplicate shape id'};$ids[$item.id]=$true
  if(!$layers.ContainsKey($item.layer)){throw "Undeclared layer: $($item.layer)"}
  if($item.kind -notin @('rect','ellipse','poly','text','connector')){throw "Unsupported shape kind: $($item.kind)"}
  if($item.kind -in @('rect','ellipse','text')){
   foreach($key in @('x','y','w','h')){if(!(Finite $item.$key)){throw "Nonfinite/missing $key"}}
   if($item.w -le 0 -or $item.h -le 0){throw 'Shape extent must be positive'}
  }
  if($item.kind -eq 'poly'){
   if(@($item.points).Count -lt 2){throw 'Polyline needs two points'}
   foreach($point in $item.points){if(@($point).Count -ne 2 -or !(Finite $point[0]) -or !(Finite $point[1])){throw 'Invalid point'}}
  }
  foreach($field in @('fromSide','toSide')){
   if((Has $item $field) -and ($item.kind -ne 'connector' -or $item.$field -notin $portOffsets.Keys)){throw "Invalid connector side: $field"}
  }
  if($item.notation -and $item.runs){throw 'Choose notation or explicit runs'}
  if((Has $item 'italic') -and $item.italic -isnot [bool]){throw 'italic must be boolean'}
  foreach($key in @('weight','size')){if((Has $item $key) -and (!(Finite $item.$key) -or $item.$key -le 0)){throw "Invalid $key"}}
  if((Has $item 'alpha') -and (!(Finite $item.alpha) -or $item.alpha -lt 0 -or $item.alpha -gt 100)){throw 'Invalid transparency'}
  foreach($key in @('line','fill','color')){if($item.$key){[void](Color $item.$key)}}
 }
 foreach($item in $scene.shapes){if($item.kind -eq 'connector' -and (!$ids.ContainsKey($item.from) -or !$ids.ContainsKey($item.to) -or $item.from -eq $item.to)){throw 'Invalid connector endpoints'}}
 foreach($ext in @('.vsdx','.png','.svg')){if((Test-Path -LiteralPath (Join-Path $out ($scene.name+$ext))) -and !$Replace){throw "Existing output: $($scene.name+$ext)"}}
}
if($null -eq [Type]::GetTypeFromProgID('Visio.InvisibleApp')){throw 'Microsoft Visio InvisibleApp COM interface is not installed/registered'}
New-Item -ItemType Directory -Path $out -Force | Out-Null
$app=$null;$doc=$null;$check=$null;$reports=@();$rasterSaved=$false;$oldRasterType=0;$oldRasterX=0.0;$oldRasterY=0.0;$oldRasterUnit=0;$exportSettings=@{};$sizeSaved=$false;$oldExportSize=0;$oldExportW=0.0;$oldExportH=0.0;$oldExportUnit=0
try{
 $app=New-Object -ComObject Visio.InvisibleApp
 $app.Settings.GetRasterExportResolution([ref]$oldRasterType,[ref]$oldRasterX,[ref]$oldRasterY,[ref]$oldRasterUnit);$rasterSaved=$true
 $app.Settings.SetRasterExportResolution(3,$RasterDpi,$RasterDpi,0)
 $app.Settings.GetRasterExportSize([ref]$oldExportSize,[ref]$oldExportW,[ref]$oldExportH,[ref]$oldExportUnit);$sizeSaved=$true
 $app.Settings.SetRasterExportSize(2,1,1,2)
 foreach($key in @('RasterExportColorFormat','RasterExportUseTransparencyColor','RasterExportTransparencyColor','RasterExportBackgroundColor','RasterExportRotation','RasterExportFlip')){$exportSettings[$key]=$app.Settings.$key}
 $app.Settings.RasterExportColorFormat=3
 $app.Settings.RasterExportBackgroundColor=16777215
 $app.Settings.RasterExportRotation=0;$app.Settings.RasterExportFlip=0
 $app.Settings.RasterExportUseTransparencyColor=($PngMode -eq 'AlphaSafe')
 foreach($scene in $scenes){
  $token=[guid]::NewGuid().ToString('N');$pending=Join-Path $out ($scene.name+'.'+$token+'.vsdx')
  $doc=$app.Documents.Add('');$page=$doc.Pages.Item(1);$page.Name='Diagram'
  Cell $page.PageSheet 'PageWidth' ((Num $scene.width)+' in');Cell $page.PageSheet 'PageHeight' ((Num $scene.height)+' in')
  $layerMap=@{};$layerMeta=@{}
  foreach($layer in $scene.layers){$layerMap[$layer.name]=$page.Layers.Add($layer.name);$layerMeta[$layer.name]=$layer}
  # A native white rectangle fixes PNG export extent to the authored page.
  $frameLayer='__page-export__'
  if($layerMap.ContainsKey($frameLayer)){throw 'Reserved export layer name'}
  $layerMap[$frameLayer]=$page.Layers.Add($frameLayer)
  $frame=$page.DrawRectangle(0,0,[double]$scene.width,[double]$scene.height)
  Cell $frame 'LinePattern' '0';Cell $frame 'FillForegnd' 'RGB(255,255,255)';Cell $frame 'FillPattern' '1'
  [void]$layerMap[$frameLayer].Add($frame,0);$frame.Data1=$frameLayer
  $shapeMap=@{};$connectors=@();$font=if($scene.font){$scene.font}else{'Arial'};$eastAsiaFont=if($scene.fontEastAsia){$scene.fontEastAsia}else{'Microsoft YaHei'}
  foreach($item in $scene.shapes){
   switch($item.kind){
    'rect' {$shape=$page.DrawRectangle([double]$item.x,[double]$item.y,([double]$item.x+[double]$item.w),([double]$item.y+[double]$item.h))}
    'text' {$shape=$page.DrawRectangle([double]$item.x,[double]$item.y,([double]$item.x+[double]$item.w),([double]$item.y+[double]$item.h))}
    'ellipse' {$shape=$page.DrawOval([double]$item.x,[double]$item.y,([double]$item.x+[double]$item.w),([double]$item.y+[double]$item.h))}
    'poly' {
     $xy=[Collections.Generic.List[double]]::new()
     foreach($point in $item.points){$xy.Add([double]$point[0]);$xy.Add([double]$point[1])}
     if($item.closed -and ($xy[0] -ne $xy[$xy.Count-2] -or $xy[1] -ne $xy[$xy.Count-1])){$xy.Add($xy[0]);$xy.Add($xy[1])}
     $shape=$page.DrawPolyline($xy.ToArray(),0)
    }
    'connector' {$shape=$page.Drop($app.ConnectorToolDataObject,0,0);$connectors+=@{shape=$shape;item=$item}}
   }
   ApplyStyle $shape $item;ApplyText $shape $item $doc $font $eastAsiaFont
   Cell $shape 'LayerMember' '""'
   [void]$layerMap[$item.layer].Add($shape,0)
   $shape.Data1=$item.layer;$shape.Data2=$item.id
   if($item.name){$shape.NameU=[string]$item.name}
   $shapeMap[$item.id]=$shape
  }
  foreach($edge in $connectors){
   GlueEndpoint ($edge.shape.CellsU('BeginX')) $shapeMap[$edge.item.from] $edge.item.fromSide
   GlueEndpoint ($edge.shape.CellsU('EndX')) $shapeMap[$edge.item.to] $edge.item.toSide
  }
  # Connector masters may create a localized default layer; keep only declared semantics.
  for($ix=$page.Layers.Count;$ix -ge 1;$ix--){$nativeLayer=$page.Layers.Item($ix);if(!$layerMap.ContainsKey([string]$nativeLayer.Name)){$nativeLayer.Delete(0)}}
  [void]$doc.SaveAs($pending)
  # Avoid the opaque PNG edge-artifact path observed on this Windows/Visio build.
  # The white export frame stays opaque; choose a transparency key absent from all source colors.
  $usedColors=@{'#FFFFFF'=$true}
  foreach($item in $scene.shapes){foreach($key in @('line','fill','color')){if($item.$key){$usedColors[[string]$item.$key]=$true}}}
  $candidate=0xFF00FF
  while($usedColors.ContainsKey(('#{0:X6}' -f $candidate))){$candidate--;if($candidate -lt 0){throw 'No unused export transparency color'}}
  $hex=('{0:X6}' -f $candidate)
  $app.Settings.RasterExportTransparencyColor=([Convert]::ToInt32($hex.Substring(0,2),16)+256*[Convert]::ToInt32($hex.Substring(2,2),16)+65536*[Convert]::ToInt32($hex.Substring(4,2),16))
  [void]$page.Export((Join-Path $out ($scene.name+'.'+$token+'.png')))
  [void]$page.Export((Join-Path $out ($scene.name+'.'+$token+'.svg')))
  $doc.Close();$doc=$null
  $check=$app.Documents.OpenEx($pending,2);$cp=$check.Pages.Item(1)
  $records=[Collections.Generic.List[object]]::new();AuditShapes $cp.Shapes $records
  $unlayered=@($records | Where-Object {$_.layer -in @('','""')}).Count
  $foreign=@($records | Where-Object {$_.kind -eq 4}).Count
  $expected=@($scene.shapes | ForEach-Object {$_.id})
  $actual=@($records | Where-Object {$_.sourceId} | ForEach-Object {$_.sourceId})
  if($actual.Count -ne $expected.Count -or @($expected | Where-Object {$_ -notin $actual}).Count -gt 0){throw 'Reopened native source-id audit failed'}
  $glued=@()
  foreach($s in $cp.Shapes){if($s.Data2 -in @($connectors | ForEach-Object {$_.item.id})){$glued+=@{id=$s.Data2;connections=$s.Connects.Count}}}
  if($unlayered -gt 0 -or $foreign -gt 0 -or @($glued | Where-Object {$_.connections -lt 2}).Count -gt 0){throw 'Native shape/layer/connector audit failed'}
  $report=[pscustomobject]@{name=$scene.name;file=(Join-Path $out ($scene.name+'.vsdx'));shapes=$records.Count;layers=$cp.Layers.Count;rasterDpi=$RasterDpi;pngMode=$PngMode;font=$font;fontEastAsia=$eastAsiaFont;unlayered=$unlayered;foreignObjects=$foreign;sourceIdsVerified=$actual.Count;connectors=$glued;symbols=@($records | Where-Object {$_.text} | ForEach-Object {$_.text});layerDefinitions=@($scene.layers);projectionDiagnostics=@($scene.projectionDiagnostics)}
  $check.Close();$check=$null
  foreach($ext in @('.vsdx','.png','.svg')){
   $final=Join-Path $out ($scene.name+$ext)
   if(Test-Path -LiteralPath $final){
    $backup=Join-Path $out ('_previous\'+$token);New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Move-Item -LiteralPath $final -Destination (Join-Path $backup ($scene.name+$ext))
   }
   Move-Item -LiteralPath (Join-Path $out ($scene.name+'.'+$token+$ext)) -Destination $final
  }
  $reports+=$report
  $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $out ($scene.name+'.audit.json')) -Encoding UTF8
  Write-Output ("Completed: "+$scene.name)
 }
 $reports | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $out 'visio-audit.json') -Encoding UTF8
}finally{
 if($null -ne $check){$check.Close()}
 if($null -ne $doc){$doc.Saved=$true;$doc.Close()}
 if($null -ne $app){try{if($rasterSaved){$app.Settings.SetRasterExportResolution($oldRasterType,$oldRasterX,$oldRasterY,$oldRasterUnit)};if($sizeSaved){if($oldExportSize -eq 3){$app.Settings.SetRasterExportSize($oldExportSize,$oldExportW,$oldExportH,$oldExportUnit)}else{$app.Settings.SetRasterExportSize($oldExportSize,1,1,2)}};foreach($key in $exportSettings.Keys){$value=$exportSettings[$key];if($value -is [uint32]){$value=[BitConverter]::ToInt32([BitConverter]::GetBytes([uint32]$value),0)};$app.Settings.$key=$value}}finally{$app.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)}}
}
