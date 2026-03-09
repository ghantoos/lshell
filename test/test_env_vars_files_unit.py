"""Unit tests for env_vars_files loading behavior in CheckConfig."""

import os
import tempfile
import unittest
from unittest.mock import patch, call

from lshell.checkconfig import CheckConfig

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestEnvVarsFilesUnit(unittest.TestCase):
    """Config-level unit tests for env_vars_files behavior."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    @patch("lshell.checkconfig.builtincmd.cmd_source", return_value=0)
    def test_checkconfig_calls_cmd_source_for_each_env_file(self, mock_cmd_source):
        """Load each configured env_vars_files entry through cmd_source."""
        files = ["/tmp/a.env", "/tmp/b.env"]
        CheckConfig(self.args + [f"--env_vars_files={files}"]).returnconf()
        self.assertEqual(
            mock_cmd_source.call_args_list,
            [call("/tmp/a.env"), call("/tmp/b.env")],
        )

    def test_env_vars_files_exports_override_env_vars(self):
        """Load env_vars first, then let env_vars_files override collisions."""
        key = "LSHELL_ENV_VARS_FILES_OVERRIDE"
        prev = os.environ.get(key)

        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write(f"export {key}=from_file\n")
            env_path = env_file.name

        try:
            CheckConfig(
                self.args
                + [
                    f"--env_vars={{'{key}':'from_conf'}}",
                    f"--env_vars_files=['{env_path}']",
                ]
            ).returnconf()
            self.assertEqual(os.environ.get(key), "from_file")
        finally:
            os.remove(env_path)
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


if __name__ == "__main__":
    unittest.main()
