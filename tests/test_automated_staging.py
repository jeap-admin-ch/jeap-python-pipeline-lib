import unittest

from src.jeap_pipeline.automated_staging import (get_next_deployment_stage)


class TestGetNextDeploymentStage(unittest.TestCase):
    def test_stage_exists(self):
        automated_staging = {
            "dev": "test",
            "test": "prod"
        }
        self.assertEqual(get_next_deployment_stage("dev", automated_staging), "test")
        self.assertEqual(get_next_deployment_stage("test", automated_staging), "prod")

    def test_stage_does_not_exist(self):
        automated_staging = {
            "dev": "test",
            "test": "prod"
        }
        self.assertIsNone(get_next_deployment_stage("prod", automated_staging))


if __name__ == "__main__":
    unittest.main()
