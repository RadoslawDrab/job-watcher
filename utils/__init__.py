def get_dict_keys(data: dict, include_dicts: bool = False, parent_key: str | None = None):
	result = []
	parent_key = parent_key + '.' if parent_key else ''
	for key, value in data.items():
		if isinstance(value, dict):
			if include_dicts:
				result.append(parent_key + key)
			result.extend(get_dict_keys(value, include_dicts, parent_key + key))
		else:
			result.append(parent_key + key)
	return result