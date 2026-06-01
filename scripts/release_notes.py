import os
import re
import urllib.request
import urllib.error
import json
from pathlib import Path

from google import genai


class ReleaseNotes:
	BASE_PATH = 'https://api.github.com/repos'
	def __init__(self, github_user_name: str, github_repo_name: str, ai_message: str, github_token: str | None = None):
		self.user_name = github_user_name
		self.repo_name = github_repo_name
		self.ai_message = ai_message
		self._github_token = github_token
		self._gemini_client = genai.Client()
	def _get_path(self, *paths: str):
		joined_path = "/".join([re.sub('^/|/$', '', p) for p in paths])
		return f'{self.BASE_PATH}/{self.user_name}/{self.repo_name}/{joined_path}'
	def _get_response(self, *paths: str) -> dict | None:
		try:
			headers = { "User-Agent": f"{self.repo_name}" }

			if self._github_token:
				headers["Authorization"] = f"token {self._github_token}"
			req = urllib.request.Request(self._get_path(*paths), headers=headers)
			with urllib.request.urlopen(req, timeout=5) as response:
				data = json.loads(response.read())
			return data
		except Exception:
			return None

	def get_tags(self) -> list[dict[str, str]]:
		return [
			{
				'sha': ref['object']['sha'],
			    'tag': ref["ref"].replace('refs/tags/', '')
			}
			for ref in self._get_response('git/refs/tags') or []
		]

	def get_commit_messages(self, between: tuple[str, str] | None = None) -> list[dict[str, str]]:
		messages = [
			{
				'sha': commit['sha'],
				'message': commit['commit']['message']
			}
			for commit in self._get_response('commits') or []
		]

		if between:
			start_index = next((index for index, message in enumerate(messages) if message['sha'] == between[0]), None)
			end_index = next((index for index, message in enumerate(messages) if message['sha'] == between[1]), None)
			if start_index is None or end_index is None:
				return []
			return messages[start_index:end_index + 1]

		return messages


	def generate_release_notes(self, commits: list[str]) -> str:
		if len(commits) == 0:
			return ""
		content = "\n\n".join(commits)
		response = self._gemini_client.models.generate_content(
			model=os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash'),
			contents=f"{self.ai_message}\n\n{content}"
		)
		return response.text

def init():
	release_notes_path = Path('RELEASE_NOTES.md')
	if release_notes_path.exists():
		with open(release_notes_path, 'r') as f:
			content = f.read()
			if len(content) > 0:
				print(content)
				return

	user_name, repo_name = os.environ.get('GITHUB_REPOSITORY', 'RadoslawDrab/job-worker').split('/')
	release_notes = ReleaseNotes(
		ai_message=os.environ.get('GEMINI_MESSAGE', 'Generate concise markdown release notes from these git commits. Group by features, fixes, and other changes. Be brief.'),
		github_user_name=user_name,
		github_repo_name=repo_name,
		github_token=os.environ.get('GITHUB_TOKEN')
	)

	tags = release_notes.get_tags()
	if len(tags) >= 2:
		last_first_tag = tags[-1]
		last_second_tag = tags[-2]
	else:
		last_first_tag = None
		last_second_tag = None

	messages = release_notes.get_commit_messages((last_first_tag['sha'], last_second_tag['sha']) if last_first_tag and last_second_tag else None)

	notes = release_notes.generate_release_notes([message['message'] for message in messages])

	print(notes)


if __name__ == "__main__":
	init()