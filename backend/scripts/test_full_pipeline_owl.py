"""
Full 6-stage pipeline test for Owl Roofing — new service page.

Runs: research → strategy → copywrite → design → images → qa
Service: Roof Replacement (Twin Cities / Shoreview, MN)

This tests the complete pipeline with all improvements:
- Brand extraction with self-hosted font detection
- Two-column image+text layouts
- Micro labels, location pills, large process numbers
- Real image generation via Recraft
- Full QA scoring
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

import anthropic
from utils.db import init_db, _connect
from memory.store import ClientMemoryStore, init_memory_table
from pipeline.engine import PipelineEngine, PipelineStatus
from pipeline.stages import STAGE_RUNNERS

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_output")
CLIENT_ID = 15
CLIENT_NAME = "Owl Roofing"
DOMAIN = "owlroofing.com"


async def main():
    init_db()
    conn = _connect()
    init_memory_table(conn)

    api_client = anthropic.AsyncAnthropic()
    store = ClientMemoryStore(_connect)
    engine = PipelineEngine(api_client, _connect, store)

    # Verify brand memory exists
    has_brand = store.has_entries(CLIENT_ID, "design_system")
    print(f"\n{'='*70}")
    print(f"  OWL ROOFING — FULL PIPELINE TEST")
    print(f"  Service: Roof Replacement | Location: Shoreview & Twin Cities, MN")
    print(f"  Brand memory: {'loaded' if has_brand else 'will auto-extract'}")
    print(f"{'='*70}\n")

    # Create the pipeline run — ALL 6 stages
    run = engine.create_run(
        page_type="service-page",
        client_id=CLIENT_ID,
        client_name=CLIENT_NAME,
        inputs={
            "domain": DOMAIN,
            "service": "roof replacement",
            "location": "Shoreview, MN",
            "keyword": "roof replacement shoreview mn",
            "competitors": "www.roofmn.com, www.harstad.com, www.bloomroofing.com",
            "differentiators": "Family-owned, GAF & Owens Corning certified, 10-year workmanship warranty, 3-Step Cleanup Guarantee, Wise Check inspection process, over-communicative approach",
            "price_range": "$8,000-$25,000 depending on roof size and materials",
            "notes": "Minnesota climate: harsh winters, ice dams, freeze-thaw cycles, hail storms. Serving Shoreview, North Oaks, Arden Hills, Roseville, New Brighton, Mounds View, and the Twin Cities metro. MN License #BC809662.",
        },
        stages=["research", "strategy", "copywrite", "design", "images", "qa"],
        approval_mode="autopilot",
    )

    print(f"  Pipeline ID: {run.pipeline_id}")
    print(f"  Stages: {' → '.join(run.stages)}\n")

    # Execute full pipeline
    stage_outputs = {}
    current_stage = None
    stage_start_time = time.time()
    total_start = time.time()

    async for chunk_json in engine.execute(run, STAGE_RUNNERS):
        data = json.loads(chunk_json)

        if data["type"] == "brand_extracted":
            print(f"  >> {data['message']}")

        elif data["type"] == "stage_start":
            current_stage = data["stage"]
            stage_outputs[current_stage] = []
            stage_start_time = time.time()
            stage_num = data["stage_index"] + 1
            total = data["total_stages"]
            rev = data.get("revision_round", 0)
            rev_label = f" (revision {rev})" if rev > 0 else ""
            print(f"\n  {'━'*60}")
            print(f"  ┃ STAGE {stage_num}/{total}: {data['stage'].upper()}{rev_label}")
            print(f"  {'━'*60}")

        elif data["type"] == "token":
            stage = data.get("stage", current_stage)
            if stage not in stage_outputs:
                stage_outputs[stage] = []
            stage_outputs[stage].append(data["text"])
            # Show progress — print a dot every 50 chunks
            count = len(stage_outputs[stage])
            if count % 50 == 0:
                print(".", end="", flush=True)

        elif data["type"] == "stage_complete":
            stage = data["stage"]
            output = "".join(stage_outputs.get(stage, []))
            elapsed = time.time() - stage_start_time
            method = data.get("method", "full")

            # Save stage output
            base_stage = stage.split("_r")[0]  # strip revision suffix
            ext = "html" if "design" in base_stage else "md"
            filepath = os.path.join(OUTPUT_DIR, f"owl_full_{stage}.{ext}")
            with open(filepath, "w") as f:
                f.write(output)

            method_label = f" [{method}]" if method != "full" else ""
            print(f"\n  ┃ {stage} complete — {len(output):,} chars in {elapsed:.0f}s{method_label}")
            print(f"  ┃ Saved: {os.path.basename(filepath)}")

        elif data["type"] == "revision_start":
            rev_round = data["round"]
            prev_score = data["previous_score"]
            threshold = data["threshold"]
            stages = data["stages_to_revise"]
            directives = data["directive_count"]
            print(f"\n  {'╔'*1}{'═'*58}{'╗'*1}")
            print(f"  ║  REVISION ROUND {rev_round} — score {prev_score} < {threshold} threshold")
            print(f"  ║  Revising: {', '.join(stages)} ({directives} directives)")
            print(f"  {'╚'*1}{'═'*58}{'╝'*1}")

        elif data["type"] == "revision_complete":
            prev = data["previous_score"]
            new = data["new_score"]
            improved = data["improved"]
            arrow = "↑" if improved else "→"
            print(f"\n  ┃ Revision {data['round']} complete: {prev} {arrow} {new}/100")

        elif data["type"] == "pipeline_complete":
            total_elapsed = time.time() - total_start
            final_score = data.get("final_score", 0)
            rev_rounds = data.get("revision_rounds", 0)
            print(f"\n\n  {'='*60}")
            print(f"  ┃ PIPELINE COMPLETE — {data['stages_completed']} stages in {total_elapsed:.0f}s")
            if rev_rounds > 0:
                print(f"  ┃ Revision rounds: {rev_rounds}")
                for h in data.get("revision_history", []):
                    print(f"  ┃   Round {h['round']}: {h['previous_score']} → {h['new_score']}")
            print(f"  ┃ Final QA score: {final_score}/100")
            print(f"  {'='*60}")

        elif data["type"] == "error":
            print(f"\n  !! ERROR in {data.get('stage', '?')}: {data['message']}")
            break

    # ── Save final outputs ──────────────────────────────────────────────

    print(f"\n  ┌─────────────────────────────────────────────────────┐")
    print(f"  │  FINAL OUTPUT                                       │")
    print(f"  └─────────────────────────────────────────────────────┘")

    # Save the final HTML (may include generated images)
    final_html = ""
    if "images" in run.artifacts:
        img_data = json.loads(run.artifacts["images"])
        final_html = img_data.get("html", "")
        images = img_data.get("images", [])
        success = sum(1 for i in images if i.get("success"))
        print(f"\n  Images: {success}/{len(images)} generated successfully")
        for img in images:
            status = "OK" if img.get("success") else "FAIL"
            print(f"    [{status}] {img.get('tool', '?')}: {img.get('prompt', '')[:60]}...")

    if not final_html and "design" in run.artifacts:
        design = json.loads(run.artifacts["design"])
        final_html = design.get("full_page", "")

    if final_html:
        html_path = os.path.join(OUTPUT_DIR, "owl_roofing_full_pipeline.html")
        with open(html_path, "w") as f:
            f.write(final_html)
        print(f"\n  Final HTML: {html_path}")
        print(f"  Size: {len(final_html):,} chars")

    # QA results
    if "qa" in run.artifacts:
        qa = json.loads(run.artifacts["qa"])
        score = qa.get("overall_score", 0)
        approved = qa.get("approved", False)
        print(f"\n  QA Score: {score}/100")
        print(f"  Verdict: {'APPROVED' if approved else 'NEEDS REVISION'}")

        # Print the review summary
        review = qa.get("review_text", "")
        if review:
            scores = re.findall(r'### (.+?):\s*(\d+)/20', review)
            if scores:
                print(f"\n  Score breakdown:")
                for cat, s in scores:
                    bar = "█" * int(s) + "░" * (20 - int(s))
                    print(f"    {cat:25s} {bar} {s}/20")

    # Open in browser
    if final_html:
        print(f"\n  Opening in browser...")
        subprocess.run(["open", html_path])

    print(f"\n  All outputs in: {OUTPUT_DIR}/")
    print(f"  Files: owl_full_research.md, owl_full_strategy.md, owl_full_copywrite.md,")
    print(f"         owl_full_design.html, owl_roofing_full_pipeline.html\n")


if __name__ == "__main__":
    asyncio.run(main())
