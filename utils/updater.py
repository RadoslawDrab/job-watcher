import urllib.request
import json
import sys
import os
import subprocess
from pathlib import Path

from utils.classes import Singleton
from utils.logger import Logger

class Updater(Singleton):
	def __init__(self, github_user_name: str, github_repo_name: str, current_version: str, tmp_dir: Path = Path.cwd().joinpath('tmp'), mock: bool = False):
		super().__init__()
		self.user_name = github_user_name
		self.repo_name = github_repo_name
		self.current_version = 'v0.0.0' if mock else current_version
		self.tmp_dir = tmp_dir
		self.mock = mock
		self._last_download_url: str | None = None
		self._last_version: str | None = None

	@classmethod
	def check(cls) -> tuple[str, str] | None:
		"""Returns (latest_version, download_url) or None if up to date."""
		self = cls._instance
		try:
			url = f"https://api.github.com/repos/{self.user_name}/{self.repo_name}/releases/latest"
			req = urllib.request.Request(url, headers={ "User-Agent": f"{self.repo_name}" })
			with urllib.request.urlopen(req, timeout=5) as response:
				data = json.loads(response.read())

			latest = data["tag_name"]
			if latest == self.current_version:
				return None

			# find asset matching current platform
			suffix = cls._get_platform_suffix()
			asset = next(
				(a for a in data["assets"] if suffix in a["name"]),
				None
			)
			if asset is None:
				return None

			self._last_version = latest
			self._last_download_url = asset["browser_download_url"]
			return str(self._last_version), str(self._last_download_url)
		except Exception as error:
			print(error)
			return None

	@classmethod
	def _get_platform_suffix(cls) -> str:
		import platform
		system = platform.system().lower()
		machine = platform.machine().lower()
		if system == "windows":
			return "windows-x64"
		if system == "darwin":
			return "macos-arm64" if machine == "arm64" else "macos-x64"
		return "linux-arm64" if machine == "aarch64" else "linux-x64"

	@classmethod
	def apply(cls, download_url: str | None = None):
		"""Download new binary, replace current executable, restart."""
		self = cls._instance
		if not self._last_download_url:
			cls.check()

		current = Path(sys.executable)
		tmp = self.tmp_dir.joinpath(current.name).with_suffix(".new")
		backup = self.tmp_dir.joinpath(current.name).with_suffix(".old")

		Logger.log("Downloading update...", force_print=True, log_type='INFO')
		try:
			req = urllib.request.Request(str(download_url or self._last_download_url), headers={ "User-Agent": self.repo_name })
			with urllib.request.urlopen(req) as response, open(tmp, "wb") as f:
				f.write(response.read())

			# swap files
			if backup.exists():
				backup.unlink()

			current.rename(backup)
			tmp.rename(current)

			# make executable on unix
			if sys.platform != "win32":
				os.chmod(current, 0o755)

			Logger.log("Update applied. Restarting...", force_print=True, log_type="INFO")
			subprocess.Popen([str(current)] + sys.argv[1:])
			sys.exit(0)

		except Exception as error:
			Logger.log(f"Update failed: {error}", log_type="ERROR")
			if tmp.exists():
				tmp.unlink()