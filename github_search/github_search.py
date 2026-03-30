import os
import requests

github_api_key = os.getenv("GITHUB_API_KEY")
headers = {"Authorization": f"Bearer {github_api_key}"} if github_api_key else {}


def format_count(n: int) -> str:
    if n >= 1000000:
        return f"{n / 1000000:.1f}m"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def search_github_projects(concept: str, language: str = "python", per_page: int = 10):
    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"{concept} language:{language} stars:>1000",
        "sort": "stars",
        "order": "desc",
        "per_page": per_page
    }

    response = requests.get(url, headers=headers, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()
    items = data.get("items", [])

    results = []
    for repo in items:
        results.append({
            "title": repo.get("name", ""),
            "author": f"@{repo.get('owner', {}).get('login', '')}",
            "description": repo.get("description") or "No description.",
            "stars": format_count(repo.get("stargazers_count", 0)),
            "forks": format_count(repo.get("forks_count", 0)),
            "tag": (repo.get("language") or "UNKNOWN").upper(),
            "isAvatar": True,
            "avatarUrl": repo.get("owner", {}).get("avatar_url", ""),
            "url": repo.get("html_url", "")
        })

    return results