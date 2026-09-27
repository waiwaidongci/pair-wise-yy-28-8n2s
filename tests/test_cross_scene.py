import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import ContinuityDB, DomainError


class CrossSceneTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=ContinuityDB(self.path)
        self.producer=self.db.add_user("制片","producer")
        self.continuity=self.db.add_user("场记","continuity")
        self.reviewer=self.db.add_user("审片","reviewer")
        self.production=self.db.create_production("跨场测试","叙事链沿用状态",self.producer)
        self.scn1=self.db.add_scene(self.production,"S01","第一场",1)
        self.scn2=self.db.add_scene(self.production,"S02","第二场",2)
        self.scn3=self.db.add_scene(self.production,"S03","第三场",3)
        self.a1=self.db.add_shot(self.scn1,"S01-01",3,1,"",self.continuity)
        self.a2=self.db.add_shot(self.scn1,"S01-02",4,2,"",self.continuity)
        self.b1=self.db.add_shot(self.scn2,"S02-01",2,1,"未重新登记伤痕",self.continuity)
        self.b2=self.db.add_shot(self.scn2,"S02-02",1,2,"伤势回退",self.continuity)
        self.c1=self.db.add_shot(self.scn3,"S03-01",5,1,"",self.continuity)
        self.injury=self.db.add_element(self.production,"手臂伤痕","injury","monotonic","只能加重")

    def tearDown(self): self.db.close(); os.unlink(self.path)

    def test_carry_forward_state_detects_regression_in_later_scene(self):
        # 第一场登记重度，第二场前半段未登记，后半段登记轻度 -> 沿用状态后应报跨场回退
        self.db.set_element_state(self.a2,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        # 只检查第二场也能发现（检测按整个项目叙事链执行）
        conflicts=self.db.check_scene(self.scn2)
        self.assertEqual(1,len(conflicts))
        c=conflicts[0]
        self.assertEqual("regression",c["kind"])
        self.assertTrue(c["cross_scene"])
        self.assertEqual(self.b2,c["to_shot_id"])
        self.assertEqual(self.a2,c["from_shot_id"])
        self.assertEqual("S01",c["from_scene_number"])
        self.assertEqual("S02",c["to_scene_number"])

    def test_carry_forward_with_no_change_is_clean(self):
        self.db.set_element_state(self.a1,self.injury,"轻度",1,"",self.continuity)
        # 第二场完全未登记，第三场登记同等数值，沿用上一次明确状态且无回退
        self.db.set_element_state(self.c1,self.injury,"轻度",1,"",self.continuity)
        self.assertEqual([],self.db.check_scene(self.scn1))
        self.assertEqual([],self.db.check_scene(self.scn2))
        self.assertEqual([],self.db.check_scene(self.scn3))

    def test_allowed_transition_is_checked_across_scenes(self):
        costume=self.db.add_element(self.production,"外套","costume","allowed","换装需登记")
        self.db.add_transition(costume,"干","湿")
        self.db.set_element_state(self.a1,costume,"湿",None,"",self.continuity)
        self.db.set_element_state(self.c1,costume,"干",None,"",self.continuity)
        conflicts=self.db.check_scene(self.scn3)
        self.assertEqual(1,len(conflicts))
        self.assertEqual("transition_not_allowed",conflicts[0]["kind"])
        self.assertTrue(conflicts[0]["cross_scene"])

    def test_open_cross_scene_conflict_blocks_both_shots(self):
        self.db.set_element_state(self.a2,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        self.db.check_scene(self.scn2)
        # 前镜头、后镜头、以及同场未直接相关的镜头都不能锁定
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.a2,self.continuity)
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.b2,self.continuity)
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.b1,self.continuity)
        # 豁免后两端均可锁定
        cid=self.db.list_production_conflicts(self.production)[0]["id"]
        self.db.approve_exemption(cid,"刻意的闪回叙事安排，允许保留伤痕误差",self.reviewer)
        self.db.lock_shot(self.a2,self.continuity)
        self.db.lock_shot(self.b2,self.continuity)

    def test_approved_plan_recalculates_downstream_scenes(self):
        self.db.set_element_state(self.a2,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b2,self.injury,"轻度",1,"",self.continuity)
        self.db.set_element_state(self.c1,self.injury,"重度",3,"",self.continuity)
        self.db.check_scene(self.scn2)
        cid=self.db.list_production_conflicts(self.production)[0]["id"]
        plan=self.db.propose_adjustment(cid,"重度",3,"把第二场伤势改回与叙事链一致",self.producer)
        self.db.review_adjustment(plan,True,self.reviewer,"通过")
        # 第二场的回退消失；第三场与修正后的状态一致，不再产生新冲突
        self.assertEqual([],self.db.list_production_conflicts(self.production))
        report=self.db.continuity_report(self.production)
        self.assertEqual([],report["open_cross_scene_conflicts"])
        self.assertEqual(0,report["open_conflicts"])
        self.assertEqual([s["scene_number"] for s in report["scenes"]],["S01","S02","S03"])
        self.assertEqual(
            [x["shot_code"] for x in report["narrative_chain"]],
            ["S01-01","S01-02","S02-01","S02-02","S03-01"],
        )

    def test_state_change_after_locked_shot_still_detected(self):
        self.db.set_element_state(self.a1,self.injury,"中度",2,"",self.continuity)
        self.db.lock_shot(self.a1,self.continuity)
        # 已锁定镜头之后的场次数值回退，仍要报出并阻止后镜头锁定
        self.db.set_element_state(self.c1,self.injury,"轻度",1,"",self.continuity)
        conflicts=self.db.list_production_conflicts(self.production)
        self.assertEqual(1,len(conflicts))
        self.assertEqual("regression",conflicts[0]["kind"])
        with self.assertRaisesRegex(DomainError,"跨场"):
            self.db.lock_shot(self.c1,self.continuity)


if __name__=="__main__": unittest.main()
