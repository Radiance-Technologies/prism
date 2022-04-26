import json

if __name__ == "__main__":
  """
  Check which names in CoqGym are not in the repos file,
  and which names in the repos file are not in CoqGym.

  This script prints the difference between the repos file
  and the actual_repos.txt file.
  """
  with open('repos.json') as json_file:
    repos = json.load(json_file)
  repo_names = [x[0] for x in repos]
  actual = [i.strip('\n') for i in open('actual_repos.txt')]
  actual_not_in_names = list(set(actual)-set(repo_names))
  names_not_in_actual = list(set(repo_names)-set(actual))
  print(sorted(actual_not_in_names), sorted(names_not_in_actual))
