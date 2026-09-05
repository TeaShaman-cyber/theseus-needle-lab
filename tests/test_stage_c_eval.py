import unittest

from scripts.build_stage_c_dataset import POLICY_STATE_SCHEMA


class StageCEvalContractTest(unittest.TestCase):
    def test_factorized_negative_can_predict_state_without_route_call(self):
        from scripts.run_stage_c_eval import classify_stage_c_response
        state={
            'applicability':'NONE','decision':'NO_CALL','tool_need':'unnecessary',
            'evidence_state':'sufficient','cost_class':'low','risk_class':'low',
        }
        response={'type':'call','function_calls':[{'name':'policy_state','arguments':state}]}
        parsed=classify_stage_c_response(response,factorized=True)
        self.assertEqual(parsed['predicted_route'],'NO_CALL')
        self.assertEqual(parsed['predicted_state'],state)

    def test_factorized_positive_keeps_state_and_route_separate(self):
        from scripts.run_stage_c_eval import classify_stage_c_response
        state={
            'applicability':'ROUTE','decision':'PROBE','tool_need':'required',
            'evidence_state':'insufficient','cost_class':'low','risk_class':'low',
        }
        response={'type':'call','function_calls':[
            {'name':'policy_state','arguments':state},
            {'name':'route','arguments':{'decision':'PROBE'}},
        ]}
        parsed=classify_stage_c_response(response,factorized=True)
        self.assertEqual(parsed['predicted_route'],'PROBE')
        self.assertEqual(parsed['predicted_state'],state)

    def test_missing_policy_state_does_not_hide_valid_observable_route(self):
        from scripts.run_stage_c_eval import classify_stage_c_response
        response={'type':'call','function_calls':[{'name':'route','arguments':{'decision':'READY'}}]}
        parsed=classify_stage_c_response(response,factorized=True)
        self.assertEqual(parsed['predicted_route'],'READY')
        self.assertEqual(parsed['predicted_state'],'INVALID')

    def test_arm_b_case_uses_policy_state_plus_route_tools(self):
        from scripts.run_stage_c_eval import build_stage_c_case
        route={'name':'route','parameters':{'type':'object','properties':{'decision':{'type':'string','enum':['PROBE','READY','UNKNOWN']}},'required':['decision']}}
        semantic={'case_id':'x','family_id':'f','split':'heldout','applicability':'none','expected_decision':None,'query':'hello'}
        case=build_stage_c_case(semantic,route,'Use route to classify:\n\n','B')
        self.assertEqual(case['tools'],[POLICY_STATE_SCHEMA,route])
        self.assertEqual(case['expected_route'],'NO_CALL')
        self.assertEqual(case['expected_state']['applicability'],'NONE')


if __name__=='__main__':
    unittest.main()

class StageCEvalCliTest(unittest.TestCase):
    def test_cli_help_runs_from_repository_root(self):
        import pathlib, subprocess
        root=pathlib.Path(__file__).resolve().parents[1]
        result=subprocess.run(['python3','scripts/run_stage_c_eval.py','--help'],cwd=root,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
