import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import ContinuityDB, DomainError

class CrossSceneTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=ContinuityDB(self.path)
        self.producer=self.db.add_user("制片","producer"); self.continuity=self.db.add_user("场记","continuity"); self.reviewer=self.db.add_user("审片","reviewer")
        self.production=self.db.create_production("跨场影片","叙事链检查",self.producer)
        self.scene1=self.db.add_scene(self.production,"S01","第一场",1)
        self.scene2=self.db.add_scene(self.production,"S02","第二场",2)
        self.scene3=self.db.add_scene(self.production,"S03","第三场",3)
        self.a1=self.db.add_shot(self.scene1,"S01-01",1,1,"",self.continuity)
        self.b1=self.db.add_shot(self.scene2,"S02-01",2,1,"本场未登记状态",self.continuity)
        self.b2=self.db.add_shot(self.scene2,"S02-02",3,2,"误回轻伤",self.continuity)
        self.c1=self.db.add_shot(self.scene3,"S03-01",4,1,"",self.continuity)
        self.injury=self.db.add_element(self.production,"手臂伤痕","injury","monotonic","只能加重")
        self.costume=self.db.add_element(self.production,"主角外套","costume","stable","必须一致")
    def tearDown(self): self.db.close(); os.unlink(self.path)

    def test_carry_forward_and_cross_scene_detection(self):
        # 第一场登记为重伤；第二场第一个镜头不登记，必须沿用前值而不是漏检
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.assertEqual([],self.db.check_scene(self.scene2))
        # 第二场后一镜头回退到轻伤：即使中间有未登记镜头，也能检出跨场冲突
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        conflicts=self.db.check_scene(self.scene2)
        self.assertEqual(1,len(conflicts))
        c=conflicts[0]
        self.assertEqual("regression",c["kind"])
        self.assertTrue(c["cross_scene"])
        self.assertEqual(self.a1,c["from_shot_id"])
        self.assertEqual(self.b2,c["to_shot_id"])
        self.assertEqual("S01-01",c["from_shot_code"])
        self.assertIn("S01",c["detail"]); self.assertIn("S02",c["detail"])

    def test_stable_rule_carried_across_scenes(self):
        self.db.set_element_state(self.a1,self.costume,"黑色风衣",None,"",self.continuity)
        self.db.set_element_state(self.c1,self.costume,"灰色卫衣",None,"",self.continuity)
        conflicts=self.db.check_scene(self.scene3)
        self.assertEqual("state_changed",conflicts[0]["kind"])
        self.assertTrue(conflicts[0]["cross_scene"])

    def test_allowed_transition_cross_scene(self):
        prop=self.db.add_element(self.production,"怀表","prop","allowed","")
        self.db.add_transition(prop,"完好","打开","剧情需要")
        self.db.set_element_state(self.a1,prop,"完好",None,"",self.continuity)
        self.db.set_element_state(self.c1,prop,"碎裂",None,"",self.continuity)
        conflicts=self.db.check_scene(self.scene3)
        self.assertEqual("transition_not_allowed",conflicts[0]["kind"])
        # 登记一个允许的转移后重算，冲突消失
        self.db.add_transition(prop,"打开","碎裂","剧情需要")
        self.db.set_element_state(self.b1,prop,"打开",None,"",self.continuity)
        self.assertEqual([],self.db.check_scene(self.scene3))

    def test_cross_scene_conflict_blocks_both_scenes_but_not_unrelated(self):
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        self.db.check_scene(self.scene2)
        # 冲突涉及的两场都不能锁定镜头（即使该镜头本身没有登记状态）
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.a1,self.continuity)
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.b1,self.continuity)
        # 与冲突无关的第三场可以锁定
        self.db.lock_shot(self.c1,self.continuity)

    def test_approved_plan_recalculates_all_affected_scenes(self):
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        conflict=self.db.check_scene(self.scene2)[0]
        plan=self.db.propose_adjustment(conflict["id"],"重度",3,"改回重伤以符合叙事链",self.continuity)
        result=self.db.review_adjustment(plan,True,self.reviewer,"通过")
        self.assertEqual([],result["conflicts"])
        self.assertEqual([],self.db.check_scene(self.scene1))
        # 所有场次均可锁定
        self.db.lock_shot(self.a1,self.continuity); self.db.lock_shot(self.b1,self.continuity)
        self.db.lock_shot(self.b2,self.continuity)

    def test_fixing_conflict_can_surface_new_downstream_conflict(self):
        # A1=3, B2=1, C1=2：A1->B2 与 B2->C1 都有问题（回退 + 回退）
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        self.db.set_element_state(self.c1,self.injury,"中度",2,"",self.continuity)
        b_conflict=self.db.check_scene(self.scene2)[0]
        # 把 B2 修成 4（比 A1 高），A1->B2 消失，但 B2(4)->C1(2) 成为新的跨场冲突
        plan=self.db.propose_adjustment(b_conflict["id"],"特重",4,"伤情其实更重",self.continuity)
        self.db.review_adjustment(plan,True,self.reviewer,"通过")
        c_conflicts=self.db.check_scene(self.scene3)
        self.assertEqual(1,len(c_conflicts))
        self.assertEqual(self.b2,c_conflicts[0]["from_shot_id"])
        self.assertEqual(self.c1,c_conflicts[0]["to_shot_id"])

    def test_exemption_allows_locking_both_scenes(self):
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        conflict=self.db.check_scene(self.scene2)[0]
        self.db.approve_exemption(conflict["id"],"第二场为回忆段落，刻意呈现旧伤",self.reviewer)
        self.db.lock_shot(self.a1,self.continuity)
        self.db.lock_shot(self.b1,self.continuity)
        self.db.lock_shot(self.b2,self.continuity)

    def test_production_report_chains_scenes_and_cross_conflicts(self):
        self.db.set_element_state(self.a1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        report=self.db.continuity_report(self.production)
        self.assertEqual(1,report["open_conflicts"])
        cross=report["cross_scene_conflicts"]
        self.assertEqual(1,len(cross))
        self.assertEqual("S01",cross[0]["from_scene_number"])
        self.assertEqual("S02",cross[0]["to_scene_number"])
        self.assertEqual("S01-01",cross[0]["from_shot_code"])
        self.assertEqual("S02-02",cross[0]["to_shot_code"])
        # 场次按叙事顺序串联，冲突挂在问题场次（第二场）
        self.assertEqual(["S01","S02","S03"],[s["scene_number"] for s in report["scenes"]])
        self.assertEqual(1,len(report["scenes"][1]["conflicts"]))
        self.assertEqual(0,len(report["scenes"][0]["conflicts"]))
        # 元素叙事链只含显式登记点
        chain=next(c for c in report["element_chains"] if c["element_name"]=="手臂伤痕")
        self.assertEqual(["S01-01","S02-02"],[p["shot_code"] for p in chain["chain"]])

if __name__=="__main__": unittest.main()
