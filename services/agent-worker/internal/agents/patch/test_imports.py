import os
import subprocess
import sys

EXAMPLES = [
    ("starter_template", None, "main"),
    ("game-builder-crew", "src", "game_builder_crew.main"),
    ("prep-for-a-meeting", None, "prep_for_a_meeting.agents"),
    ("recruitment", "src", "recruitment.main"),
    ("markdown_validator", "src", "markdown_validator.main"),
    ("instagram_post", None, "instagram_post.agents"),
    ("job-posting", "src", "job_posting.main"),
    ("landing_page_generator", "src", "landing_page_generator.main"),
    ("marketing_strategy", "src", "marketing_posts.main"),
    ("match_profile_to_positions", "src", "match_to_proposal.main"),
    ("meta_quest_knowledge", "src", "meta_quest_knowledge.main"),
    ("screenplay_writer", None, None),
    ("stock_analysis", "src", "stock_analysis.main"),
    ("surprise_trip", "src", "surprise_travel.main"),
    ("trip_planner", None, "main"),
]

base = "/workspace/crews"
results = {}

for ex, subdir, mod in EXAMPLES:
    path = os.path.join(base, ex)
    print(f"===== {ex} =====")
    if not os.path.isdir(path):
        results[ex] = "missing"
        continue

    env = os.environ.copy()
    pp = []
    if subdir:
        pp.append(os.path.join(path, subdir))
    else:
        pp.append(base)
    env["PYTHONPATH"] = ":".join(pp)

    sync = subprocess.run(
        ["timeout", "240", "uv", "sync", "--no-dev"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
    )
    if sync.returncode != 0:
        print("uv sync failed")
        print(sync.stderr[-500:] if sync.stderr else "")
        results[ex] = f"sync_failed:{sync.returncode}"
        continue

    comp = subprocess.run(
        ["python", "-m", "compileall", "-q", "-x", r"/\.venv/", "."],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
    )
    if comp.returncode != 0:
        out = (comp.stdout or "").strip()[-800:]
        err = (comp.stderr or "").strip()[-400:]
        print(f"compile failed (rc={comp.returncode}):")
        print("stdout:", out)
        print("stderr:", err)
        results[ex] = f"compile_failed:rc={comp.returncode} out={out} err={err}"
        continue

    if mod is None:
        print("compile OK (import skipped)")
        results[ex] = "ok_compile_only"
        continue

    venv_python = os.path.join(path, ".venv", "bin", "python")
    if not os.path.isfile(venv_python):
        print("venv python not found")
        results[ex] = "no_venv_python"
        continue

    try:
        imp = subprocess.run(
            [venv_python, "-c", f"import {mod}"],
            cwd=path,
            env=env,
            timeout=30,
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"imported {mod} OK")
        results[ex] = "ok"
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()[-500:]
        print(f"import failed: {err}")
        results[ex] = f"import_failed:{err}"
    except Exception as e:
        print(f"import error: {e}")
        results[ex] = f"error:{e}"

print("\n=== Summary ===")
for ex, res in results.items():
    print(f"{ex}: {res}")
