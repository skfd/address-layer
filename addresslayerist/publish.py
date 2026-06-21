"""Publish build/site/ to the orphan gh-pages branch (single commit, force-push).

The tile pyramid is hundreds of thousands of files. To avoid copying them all
into a worktree, this stages them in place with a temporary index and
GIT_WORK_TREE, builds an orphan commit with git plumbing, and force-pushes it.
Each publish replaces the branch tip, so repository history never grows.
"""

import os
import subprocess
from datetime import date


def publish(cfg):
    """Commit build/site/ as a single orphan commit on gh-pages and force-push."""
    if not os.path.isdir(cfg.site_dir):
        raise RuntimeError(f"No site to publish: {cfg.site_dir}. Run 'site' first.")
    git_dir = os.path.join(cfg.project_dir, ".git")
    if not os.path.isdir(git_dir):
        raise RuntimeError(
            f"No git repo at {cfg.project_dir}. Run 'git init' and add an "
            f"'origin' remote before publishing."
        )

    index = os.path.join(cfg.build_dir, ".gh-pages-index")
    env = {
        **os.environ,
        "GIT_DIR": git_dir,
        "GIT_WORK_TREE": cfg.site_dir,
        "GIT_INDEX_FILE": index,
    }
    if os.path.exists(index):
        os.remove(index)

    print("Staging site files ...")
    _git(cfg, ["add", "-A"], env)
    tree = _git(cfg, ["write-tree"], env).strip()
    commit = _git(
        cfg, ["commit-tree", tree, "-m", f"site {date.today().isoformat()}"], env
    ).strip()
    _git(cfg, ["update-ref", "refs/heads/gh-pages", commit], env)

    print("Force-pushing gh-pages ...")
    _git(cfg, ["push", "--force", "origin", "gh-pages"], env)

    os.remove(index)
    print("Published to the gh-pages branch.")


def _git(cfg, args, env):
    result = subprocess.run(
        ["git", *args],
        cwd=cfg.project_dir,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout
