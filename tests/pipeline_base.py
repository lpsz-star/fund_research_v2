import unittest

from tests.pipeline_legacy import PipelineTest as LegacyPipelineTest


class PipelineTestBase(unittest.TestCase):
    """Shared helpers for grouped pipeline tests without changing test logic."""

    _base_config = LegacyPipelineTest._base_config
    _write_config = LegacyPipelineTest._write_config
    _scoped_output_dir = LegacyPipelineTest._scoped_output_dir
    _scoped_raw_dir = LegacyPipelineTest._scoped_raw_dir
