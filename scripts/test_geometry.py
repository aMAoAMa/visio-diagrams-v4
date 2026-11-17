"""Behavioral invariants; run python -m unittest discover -s scripts -p test_geometry.py."""
import copy
import math
import unittest
from project_scene3d import (Camera, IDENTITY, add, compile_scene, cross, dot,
    face_normal, frame_diagnostic, hidden_intervals, mesh_geometry, mv, norm,
    orientation, resolve_poses, rotation, sub, suggest_cameras)

def scene():
    return dict(name='test', width=8, height=6,
        layers=[dict(name='body', owner='body', concept='entity'), dict(name='axes', owner='body', concept='coordinate')],
        camera=dict(eye=[4,-6,5], target=[0,0,0], up=[0,0,1], origin=[4,3]), primitives=[])

class GeometryTests(unittest.TestCase):
    def near(self, a, b):
        for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=6)
    def test_rotation_righthanded(self):
        r=rotation([23,-17,62]); cols=[mv(r,e) for e in IDENTITY]
        self.near(cross(cols[0],cols[1]),cols[2])
        for a in cols: self.assertAlmostEqual(norm(a),1)
    def test_parent_point_and_direction(self):
        o,r=resolve_poses({'body':dict(origin=[2,3,4],euler_deg=[0,0,90]), 'sensor':dict(parent='body',origin=[1,0,0])})['sensor']
        self.near(o,[2,4,4]); self.near(mv(r,[1,0,0]),[0,1,0])
    def test_cycle_and_unknown(self):
        for p in ({'a':dict(parent='b'),'b':dict(parent='a')},{'a':dict(parent='missing')}):
            with self.assertRaises(ValueError): resolve_poses(p)
    def test_reflection_and_scaled_matrix_rejected(self):
        for r in ([[1,0,0],[0,1,0],[0,0,-1]],[[2,0,0],[0,1,0],[0,0,1]]):
            with self.assertRaises(ValueError): orientation(dict(matrix=r))
    def test_quaternion_matches_euler(self):
        r=orientation(dict(quaternion_xyzw=[0,0,math.sin(math.pi/4),math.cos(math.pi/4)]))
        self.near(mv(r,[1,0,0]),[0,1,0])
        with self.assertRaises(ValueError): orientation(dict(quaternion_xyzw=[0,0,0,2]))
    def test_invalid_cameras(self):
        for c in (dict(eye=[0,0,0]),dict(eye=[0,0,2],up=[0,0,1]),dict(eye=[2,0,0],scale=0),dict(eye=[float('nan'),0,0])):
            with self.assertRaises(ValueError): Camera(c)
    def test_perspective_shrinks_with_distance(self):
        c=Camera(dict(eye=[0,0,0],target=[0,0,1],up=[0,1,0],projection='perspective',focal_length=1))
        self.assertAlmostEqual(abs(c.project([1,0,2])[0]),abs(c.project([1,0,4])[0])*2)
    def test_near_clip_line_and_face(self):
        c=Camera(dict(eye=[0,0,0],target=[0,0,1],up=[0,1,0],projection='perspective',near=1))
        a,b,oa,ob=c.clip_line([1,0,-1],[1,0,3]); self.near(a,[1,0,1]); self.assertFalse(oa); self.assertTrue(ob)
        self.assertIsNone(c.clip_line([0,0,-2],[0,0,.5]))
        ps=c.clip_face([[-1,-1,.5],[1,-1,2],[0,1,2]])
        self.assertEqual(len(ps),4); self.assertTrue(all(c.depth(p)>=1-1e-8 for p in ps))
    def test_box_outward_winding(self):
        vs,faces=mesh_geometry(dict(kind='box',size3d=[2,4,6]))
        for face in faces:
            ps=[vs[i] for i in face]; self.assertGreater(dot(face_normal(ps),ps[0]),0)
    def test_cylinder_outward_winding(self):
        vs,faces=mesh_geometry(dict(kind='cylinder',axis=[1,2,3],radius=.5,length=2))
        for face in faces:
            ps=[vs[i] for i in face]; self.assertGreater(dot(face_normal(ps),ps[0]),0)
    def test_nonplanar_and_concave_faces_rejected(self):
        for ps in ([[0,0,0],[1,0,0],[1,1,.2],[0,1,0]],[[0,0,0],[2,0,0],[1,.5,0],[2,2,0],[0,2,0]]):
            with self.assertRaises(ValueError): face_normal(ps)
    def test_face_normal_stable_with_large_world_offset(self):
        ps=[[1e9,1e9,1e9],[1e9+1,1e9,1e9],[1e9+1,1e9+1,1e9],[1e9,1e9+1,1e9]]
        self.near(face_normal(ps),[0,0,1])
    def test_partial_occlusion(self):
        triangles=[([[0,-1],[1,-1],[0,1]],[-2,-2,-2])]
        hs=hidden_intervals([-1,0],[2,0],-3,-3,triangles)
        self.assertEqual(len(hs),1); self.near(hs[0],[1/3,.5])
        self.assertEqual(hidden_intervals([-1,0],[2,0],-1,-1,triangles),[])
    def test_equal_depth_not_self_occluded(self):
        self.assertEqual(hidden_intervals([.1,.1],[.2,.2],-2,-2,[([[0,0],[1,0],[0,1]],[-2,-2,-2])]),[])
    def test_depth_crossing_splits_inside_triangle(self):
        hs=hidden_intervals([.1,.1],[.5,.1],1,.1,[([[0,0],[1,0],[0,1]],[.5,.5,.5])])
        self.assertEqual(len(hs),1); self.assertAlmostEqual(hs[0][0],5/9,places=5); self.assertAlmostEqual(hs[0][1],1)
    def test_overlapping_occluders_merge(self):
        t=([[0,-1],[2,-1],[0,2]],[-2,-2,-2]); hs=hidden_intervals([.1,0],[.8,0],-3,-3,[t,t]); self.assertEqual(hs,[(0.,1.)])
    def test_hidden_tip_does_not_gain_arrow(self):
        s=scene(); s['camera']=dict(eye=[0,0,5],up=[0,1,0],origin=[4,3])
        s['primitives']=[dict(id='box',kind='box',layer='body',size3d=[2,2,2],fill='#AABBCC'),dict(id='force',kind='arrow',layer='axes',points=[[-3,0,0],[0,0,0]],hidden='dash')]
        out=compile_scene(s); lines=[a for a in out['shapes'] if a['id'].startswith('force')]
        self.assertTrue(any(a.get('dash') for a in lines)); self.assertFalse(any(a.get('endArrow') for a in lines))
    def test_visible_tip_only_has_one_arrow(self):
        s=scene(); s['camera']=dict(eye=[0,0,5],up=[0,1,0],origin=[4,3])
        s['primitives']=[dict(id='box',kind='box',layer='body',size3d=[2,2,2],fill='#AABBCC'),dict(id='force',kind='arrow',layer='axes',points=[[-3,0,0],[3,0,0]],hidden='dash')]
        lines=[a for a in compile_scene(s)['shapes'] if a['id'].startswith('force')]
        self.assertEqual(sum(bool(a.get('endArrow')) for a in lines),1)
    def test_transparent_mesh_does_not_occlude(self):
        s=scene(); s['camera']=dict(eye=[0,0,5],up=[0,1,0],origin=[4,3])
        s['primitives']=[dict(id='box',kind='box',layer='body',size3d=[2,2,2],fill='#AABBCC',alpha=40),dict(id='force',kind='arrow',layer='axes',points=[[-3,0,0],[3,0,0]])]
        lines=[a for a in compile_scene(s)['shapes'] if a['id'].startswith('force')]; self.assertEqual(len(lines),1); self.assertTrue(lines[0]['endArrow'])
    def test_view_isolation(self):
        s=scene(); s['views']={'inset':s['camera']}
        s['primitives']=[dict(id='box',kind='box',layer='body',size3d=[20,20,20],fill='#AABBCC'),dict(id='force',kind='arrow',layer='axes',points=[[0,0,0],[1,0,0]],view='inset')]
        self.assertTrue(any(a['id']=='force' for a in compile_scene(s)['shapes']))
    def test_duplicate_ids_and_layers(self):
        s=scene(); a=dict(id='line',kind='arrow',layer='axes',points=[[0,0,0],[1,0,0]]); s['primitives']=[a,a]
        with self.assertRaises(ValueError): compile_scene(s)
        s=scene(); s['layers'].append(dict(name='body2',owner='body',concept='entity'))
        with self.assertRaises(ValueError): compile_scene(s)
    def test_arc_righthand_and_continuity(self):
        s=scene(); s['primitives']=[dict(id='moment',kind='arc',layer='axes',center=[0,0,0],normal=[0,0,1],start_direction=[1,0,0],radius=1,sweep_deg=90)]
        out=compile_scene(s)['shapes']; self.assertEqual(len(out),1); c=Camera(s['camera'])
        self.near(out[0]['points'][0],c.project([1,0,0])); self.near(out[0]['points'][-1],c.project([0,1,0])); self.assertTrue(out[0]['endArrow'])
    def test_bad_axis_view_is_diagnosed(self):
        c=Camera(dict(eye=[5,0,0],up=[0,0,1])); d=frame_diagnostic(c,[0,0,0],IDENTITY,[1,1,1]); self.assertLess(d['length_ratio'],.01)
    def test_camera_suggestions_do_not_mutate_geometry(self):
        s=scene(); s['primitives']=[dict(id='frame',kind='frame',layer='axes')]; before=copy.deepcopy(s); candidates=suggest_cameras(s)
        self.assertEqual(s,before); self.assertEqual(len(candidates),5); self.assertGreater(candidates[0]['frames'][0]['length_ratio'],.3)
    def test_world_vector_at_body_application_point(self):
        s=scene(); s['poses']={'body':dict(origin=[2,0,0],euler_deg=[0,0,90])}
        s['primitives']=[dict(id='F',kind='vector',layer='axes',pose='body',anchor=[1,0,0],vector_pose='world',components=[0,0,-2],length_scale=.5)]
        line=compile_scene(s)['shapes'][0]; c=Camera(s['camera'])
        self.near(line['points'][0],c.project([2,1,0])); self.near(line['points'][-1],c.project([2,1,-1]))
    def test_perspective_occlusion_agrees_with_ray_depth(self):
        c=Camera(dict(eye=[0,0,0],target=[0,0,1],up=[0,1,0],projection='perspective',focal_length=1))
        tri3=[[-2,-2,2],[3,-2,4],[0,3,3]]; tri=[c.project(p) for p in tri3]; qs=[c.metric(p) for p in tri3]
        a,b=[-1,0,3],[1,0,3]; xa,xb=c.project(a),c.project(b)
        intervals=hidden_intervals(xa,xb,c.metric(a),c.metric(b),[(tri,qs)])
        normal=cross(sub(tri3[1],tri3[0]),sub(tri3[2],tri3[0]))
        for k in range(1,100):
            t=k/100; p=add(a,[(b[i]-a[i])*t for i in range(3)])
            face_depth=dot(normal,tri3[0])/dot(normal,p)*p[2]
            if abs(face_depth-3)<1e-5: continue
            hidden=any(lo<t<hi for lo,hi in intervals)
            self.assertEqual(hidden,face_depth<3)

if __name__=='__main__': unittest.main()
