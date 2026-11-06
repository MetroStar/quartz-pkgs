from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load(
    (ROOT / ".github/workflows/sync-image-manifest.yaml").read_text()
)


class ManifestSyncTests(unittest.TestCase):
    def test_schedule_and_manual_sync_do_not_need_a_cross_repository_token(self):
        events = WORKFLOW["on"]
        self.assertEqual(events["schedule"], [{"cron": "17 * * * *"}])
        self.assertEqual(
            events["workflow_dispatch"]["inputs"]["quartz_ref"]["default"], "main"
        )
        self.assertNotIn("QUARTZ_PKGS_DISPATCH_TOKEN", str(WORKFLOW))
        self.assertEqual(WORKFLOW["permissions"], {"contents": "read"})

    def test_untrusted_prs_validate_without_running_the_writer(self):
        self.assertIn("pull_request", WORKFLOW["on"])
        job = WORKFLOW["jobs"]["extract-and-update"]
        self.assertEqual(job["needs"], "validate-workflow")
        self.assertEqual(
            job["if"],
            "github.repository == 'MetroStar/quartz-pkgs' && github.event_name != 'pull_request'",
        )
        self.assertFalse(WORKFLOW["concurrency"]["cancel-in-progress"])
        self.assertEqual(job["timeout-minutes"], 30)

    def test_sync_reads_upstream_and_updates_the_canonical_package_branch(self):
        job = WORKFLOW["jobs"]["extract-and-update"]
        steps = {step["name"]: step for step in job["steps"]}
        self.assertEqual(steps["Checkout quartz-pkgs"]["with"]["ref"], "main")
        self.assertEqual(
            steps["Checkout quartz"]["with"]["repository"], "MetroStar/quartz"
        )
        self.assertEqual(
            steps["Checkout quartz"]["with"]["ref"], "${{ env.QUARTZ_REF }}"
        )
        self.assertEqual(
            steps["Checkout quartz"]["with"]["ssh-key"],
            "${{ secrets.QUARTZ_SOURCE_SSH_KEY }}",
        )
        self.assertFalse(steps["Checkout quartz"]["with"]["persist-credentials"])
        self.assertIn("git push", steps["Commit and push"]["run"])
        self.assertIn("${QUARTZ_REF}", steps["Commit and push"]["run"])
        self.assertNotIn("${{", steps["Commit and push"]["run"])

    def test_bot_commits_explicitly_dispatch_the_mirror_workflow(self):
        job = WORKFLOW["jobs"]["extract-and-update"]
        self.assertEqual(job["permissions"]["actions"], "write")
        self.assertEqual(job["permissions"]["contents"], "write")
        steps = {step["name"]: step for step in job["steps"]}
        self.assertEqual(
            steps["Start image mirroring"]["if"],
            steps["Commit and push"]["if"],
        )
        self.assertEqual(
            steps["Start image mirroring"]["env"]["GH_TOKEN"], "${{ github.token }}"
        )
        self.assertIn(
            'gh workflow run ironbank.yaml --repo "$GITHUB_REPOSITORY" --ref main',
            steps["Start image mirroring"]["run"],
        )


if __name__ == "__main__":
    unittest.main()
