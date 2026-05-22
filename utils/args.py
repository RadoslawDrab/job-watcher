import argparse
from pathlib import Path

from utils.classes import Singleton
from utils.logger import LOG_TYPES


class Args(Singleton):
	# log_level: str = 'INFO'
	# upload_dir: Path = Path('../upload')
	# output_dir: Path = Path('../output')
	# log_path: Path = Path('./logs/teo-carts-converter.log')
	config_path: Path = Path('./config.yml')
	def __new__(cls, *args, **kwargs):
		super().__new__(cls)
		parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

		# self._parser.add_argument("--upload-dir", "-u", type=Path, default=self.upload_dir, help="Upload directory")
		# self._parser.add_argument("--output-dir", "-o", type=Path, default=self.output_dir, help="Output directory")
		# self._parser.add_argument("--log-path", type=Path, default=self.log_path, help="Logs file path. File extension must be .log")
		# self._parser.add_argument("--log-level", type=str, default=self.log_level, help="Log level", choices=LOG_TYPES)
		parser.add_argument("--config-path", '-c', type=Path, default=cls.config_path, help="Config path. File extension must be .yml or .yaml")

		for key, value in parser.parse_args().__dict__.items():
			if not hasattr(cls, key) or key.startswith('_'):
				continue

			setattr(cls, key, value)
	def __repr__(self):
		return f"{self.__class__.__name__}({', '.join(f'{key}={value}' for key, value in self.__dict__.items() if not key.startswith('_'))})"