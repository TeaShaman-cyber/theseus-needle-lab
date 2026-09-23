import json
import pathlib, sqlite3, tempfile, unittest
from scripts.inventory_needle3_multiprovider_corpus import SourceSpec, build_inventory, source_inventory

def make_db(path, adapter, with_tool, branch=False):
    conn=sqlite3.connect(path)
    conn.executescript("""
    create table corpus_meta(key text primary key,value text not null);
    create table sessions(session_id text primary key,title text not null,coverage_state text not null,coverage_reason text not null,first_message_time real,last_message_time real,first_accepted_at text,last_accepted_at text,title_source_time real,title_source_artifact_sha256 text);
    create table artifacts(artifact_id integer primary key,sha256 text not null unique,size_bytes integer not null,source_schema text not null,source_adapter text not null,original_filename text,observed_title text not null,accepted_at text not null,coverage_state text not null,session_id text not null,ledger_sha256 text not null,observed_min_time real,observed_max_time real,observed_message_count integer not null);
    create table payload_pages(page_id integer primary key,artifact_id integer not null,session_id text not null,capture_sequence integer not null,member_name text not null,start_cursor text,end_cursor text,has_previous_page integer not null,has_next_page integer not null,message_count integer not null,min_create_time real,max_create_time real);
    create table messages(row_id integer primary key,session_id text not null,ordinal integer not null,message_id text,local_identity text not null,canonical_message_sha256 text not null,role text not null,content_type text not null,search_class text not null,create_time real,text text not null,provider_order integer);
    create table message_sources(message_row_id integer not null,page_id integer not null,page_position integer not null,source_message_id text,source_object_sha256 text not null,primary key(message_row_id,page_id,page_position));
    """)
    conn.execute("insert into corpus_meta values('schema_version','session-search-corpus-v1')")
    sid="s1~branch-a" if branch else "s1"
    conn.execute("insert into sessions(session_id,title,coverage_state,coverage_reason) values(?,?,?,?)",(sid,"fixture","COMPLETE_EXPOSED_CONVERSATION","fixture"))
    n=4 if with_tool else 3
    conn.execute("insert into artifacts(artifact_id,sha256,size_bytes,source_schema,source_adapter,original_filename,observed_title,accepted_at,coverage_state,session_id,ledger_sha256,observed_message_count) values(1,?,?,?,?,?,?,?,?,?,?,?)",("a"*64,1,"fixture",adapter,"fixture.zip","fixture","2026-09-23T00:00:00Z","COMPLETE_EXPOSED_CONVERSATION",sid,"b"*64,n))
    conn.execute("insert into payload_pages(page_id,artifact_id,session_id,capture_sequence,member_name,has_previous_page,has_next_page,message_count) values(1,1,?,0,'page',0,0,?)",(sid,n))
    rows=[
      (1,sid,0,"m1","l1","1"*64,"user","text","dialogue","ask"),
      (2,sid,1,"m2","l2","2"*64,"assistant","thoughts","hidden","secret"),
      (3,sid,2,"m3","l3","3"*64,"assistant","text","dialogue","answer")]
    if with_tool:
        rows.append((4,sid,3,"m4","l4","4"*64,"tool","execution_output","evidence","result"))
    conn.executemany("insert into messages(row_id,session_id,ordinal,message_id,local_identity,canonical_message_sha256,role,content_type,search_class,text) values(?,?,?,?,?,?,?,?,?,?)",rows)
    for pos,row in enumerate(rows):
        conn.execute("insert into message_sources values(?,?,?,?,?)",(row[0],1,pos,row[3],f"src-{row[0]}"))
    conn.commit(); conn.close()

class Tests(unittest.TestCase):
    def test_observable_episode_and_hidden_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"a.sqlite3"
            make_db(p,"chatgpt-export",True,True)
            r,_,_=source_inventory(SourceSpec("chatgpt",p,"chatgpt-export"))
            self.assertEqual(r["messages"]["selected"],4)
            self.assertEqual(r["messages"]["hidden_excluded_from_projection"],1)
            self.assertEqual(r["candidate_episodes"]["eligible_user_turn_episodes"],1)
            self.assertEqual(r["candidate_episodes"]["episodes_with_observed_tool_evidence"],1)
            self.assertEqual(r["sessions"]["branch_session_ids"],1)
            self.assertEqual(r["candidate_episodes"]["tool_observability"],"EXPOSED")

    def test_no_tool_evidence_does_not_become_no_call(self):
        with tempfile.TemporaryDirectory() as td:
            td=pathlib.Path(td)
            a=td/"a.sqlite3"; b=td/"b.sqlite3"
            make_db(a,"chatgpt-export",False)
            make_db(b,"xai-export",False)
            held=td/"held.jsonl"; held.write_text('{"case_id":"x"}\n')
            inv=build_inventory([SourceSpec("chatgpt",a,"chatgpt-export"),SourceSpec("xai",b,"xai-export")],[held])
            self.assertEqual(inv["decision_label_inventory"]["state"],"NOT_ADJUDICATED")
            self.assertIsNone(inv["decision_label_inventory"]["NO_CALL"])
            self.assertFalse(inv["projection_policy"]["no_observed_tool_evidence_means_no_call"])
            self.assertFalse(inv["next_gate"]["training_authorized"])

    def test_adapter_filter_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"a.sqlite3"
            make_db(p,"deepseek-export",False)
            with self.assertRaisesRegex(ValueError,"selected zero messages"):
                source_inventory(SourceSpec("chatgpt",p,"chatgpt-export"))

if __name__=="__main__":
    unittest.main()

class CandidateSelectionContractTests(unittest.TestCase):
    def test_candidate_selection_contract_is_balanced_metadata_only_and_non_authoritative(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        contract = json.loads(
            (root / "experiments/needle3-multiprovider-corpus/v1/candidate-selection-contract.json").read_text()
        )
        inventory = root / contract["inventory_binding"]["path"]
        import hashlib
        observed = hashlib.sha256(inventory.read_bytes()).hexdigest()
        self.assertEqual(observed, contract["inventory_binding"]["sha256"])
        self.assertEqual(contract["provider_quotas"], {
            "chatgpt": 300,
            "deepseek": 300,
            "xai": 300,
        })
        self.assertEqual(contract["labels"]["state"], "NOT_ADJUDICATED")
        self.assertFalse(contract["labels"]["historical_provider_action_is_ground_truth"])
        self.assertEqual(contract["privacy"]["shortlist_output"], "METADATA_ONLY_NO_RAW_TEXT")
        self.assertFalse(contract["next_gate"]["training_authorized"])
        self.assertEqual(
            contract["source_lifecycle"]["session_search_role"],
            "ONE_SHOT_EXPORT_SOURCE",
        )
        self.assertFalse(
            contract["source_lifecycle"]["live_session_search_runtime_required_after_materialization"]
        )
        self.assertEqual(
            contract["source_lifecycle"]["post_materialization_authority"],
            "FROZEN_SHORTLIST_AND_BOUND_MANIFEST",
        )


class ShortlistMaterializationTests(unittest.TestCase):
    def test_materialized_shortlist_is_deterministic_metadata_only_and_balanced(self):
        from scripts.inventory_needle3_multiprovider_corpus import SourceSpec, materialize_shortlist
        with tempfile.TemporaryDirectory() as td:
            td=pathlib.Path(td)
            sources=[]
            for provider,adapter,tool in (
                ("chatgpt","chatgpt-export",False),
                ("deepseek","deepseek-export",True),
                ("xai","xai-export",False),
            ):
                path=td/f"{provider}.sqlite3"
                make_db(path,adapter,tool)
                sources.append(SourceSpec(provider,path,adapter))
            rows,counts=materialize_shortlist(
                sources,
                {"chatgpt":1,"deepseek":1,"xai":1},
                "fixture-salt",
            )
            self.assertEqual(counts,{"chatgpt":1,"deepseek":1,"xai":1})
            self.assertEqual(len(rows),3)
            self.assertTrue(all(row["decision_label"] is None for row in rows))
            self.assertTrue(all(row["label_state"]=="NOT_ADJUDICATED" for row in rows))
            forbidden={"text","query","answer","content"}
            self.assertTrue(all(not (forbidden & set(row)) for row in rows))
            rows2,counts2=materialize_shortlist(
                sources,
                {"chatgpt":1,"deepseek":1,"xai":1},
                "fixture-salt",
            )
            self.assertEqual(rows,rows2)
            self.assertEqual(counts,counts2)


class StableSqliteBindingTests(unittest.TestCase):
    def test_nonempty_wal_is_captured_by_stable_backup(self):
        from scripts.inventory_needle3_multiprovider_corpus import SourceSpec, source_inventory
        with tempfile.TemporaryDirectory() as td:
            db=pathlib.Path(td)/"a.sqlite3"
            make_db(db,"chatgpt-export",False)
            writer=sqlite3.connect(db)
            try:
                writer.execute("pragma journal_mode=WAL")
                writer.execute("insert into corpus_meta values('fixture_commit','visible_in_wal')")
                writer.commit()
                wal=pathlib.Path(str(db)+"-wal")
                self.assertTrue(wal.is_file())
                self.assertGreater(wal.stat().st_size,0)
                report,_,_=source_inventory(SourceSpec("chatgpt",db,"chatgpt-export"))
            finally:
                writer.close()
            self.assertEqual(report["database"]["binding_mode"],"STABLE_SQLITE_BACKUP")
            self.assertEqual(len(report["database"]["sha256"]),64)

    def test_snapshot_is_immutable_after_source_commit(self):
        from scripts.inventory_needle3_multiprovider_corpus import sha256_file, stable_sqlite_snapshot
        with tempfile.TemporaryDirectory() as td:
            db=pathlib.Path(td)/"a.sqlite3"
            make_db(db,"chatgpt-export",False)
            with stable_sqlite_snapshot(db) as snapshot:
                before=sha256_file(snapshot)
                writer=sqlite3.connect(db)
                try:
                    writer.execute("insert into corpus_meta values('after_snapshot','new_source_state')")
                    writer.commit()
                finally:
                    writer.close()
                self.assertEqual(sha256_file(snapshot),before)
                snap=sqlite3.connect(snapshot)
                try:
                    row=snap.execute("select value from corpus_meta where key='after_snapshot'").fetchone()
                finally:
                    snap.close()
                self.assertIsNone(row)


class ProjectionSignatureTests(unittest.TestCase):
    def test_trace_only_context_does_not_change_episode_signature(self):
        from scripts.inventory_needle3_multiprovider_corpus import episode_records
        def row(ordinal, role, content_type, search_class, digest):
            return {
                "session_id":"s1",
                "ordinal":ordinal,
                "role":role,
                "content_type":content_type,
                "search_class":search_class,
                "canonical_message_sha256":digest,
            }
        base=[
            row(0,"user","text","dialogue","1"*64),
            row(1,"assistant","text","dialogue","2"*64),
        ]
        with_trace=base+[row(2,"unknown","user_editable_context","trace","3"*64)]
        a=episode_records(base,"chatgpt","salt")
        b=episode_records(with_trace,"chatgpt","salt")
        self.assertEqual(a[0]["episode_signature"],b[0]["episode_signature"])
        self.assertFalse(a[0]["observed_trace"])
        self.assertTrue(b[0]["observed_trace"])
