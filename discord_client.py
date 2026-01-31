import time
import requests
import logging

logger = logging.getLogger(__name__)

class DiscordClient:
    """
    A synchronous Discord API client for archiving purposes.
    Uses requests/REST API directly to avoid async complexity in Streamlit.
    """
    BASE_URL = "https://discord.com/api/v10"

    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }

    def _request(self, method, endpoint, params=None):
        url = f"{self.BASE_URL}{endpoint}"
        retries = 3
        
        for attempt in range(retries):
            response = requests.request(method, url, headers=self.headers, params=params)
            
            if response.status_code == 429:
                retry_after = response.json().get('retry_after', 1)
                logger.warning(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
                
            if response.status_code != 200:
                logger.error(f"API Error {response.status_code}: {response.text}")
            
            return response
            
        return None

    def get_guilds(self):
        """Fetch all guilds the bot is in."""
        res = self._request("GET", "/users/@me/guilds")
        if res and res.status_code == 200:
            return res.json()
        return []

    def get_channels(self, guild_id):
        """Fetch all channels for a guild."""
        res = self._request("GET", f"/guilds/{guild_id}/channels")
        if res and res.status_code == 200:
            # Filter for text channels (0) and news (5)
            # 4 is category
            all_chans = res.json()
            
            # Helper to map category IDs to names
            categories = {c['id']: c['name'] for c in all_chans if c['type'] == 4}
            
            final_channels = []
            for c in all_chans:
                if c['type'] in (0, 5): # Text or News
                    cat_id = c.get('parent_id')
                    cat_name = categories.get(cat_id, "Uncategorized")
                    final_channels.append({
                        "id": c['id'],
                        "name": c['name'],
                        "category": cat_name
                    })
            return final_channels
        return []

    def get_messages(self, channel_id, limit=None):
        """
        Fetch messages from a channel.
        Yields batches of messages to handle pagination.
        """
        params = {"limit": 100}
        last_id = None
        
        count = 0
        while True:
            if last_id:
                params["before"] = last_id
                
            res = self._request("GET", f"/channels/{channel_id}/messages", params=params)
            if not res or res.status_code != 200:
                break
                
            batch = res.json()
            if not batch:
                break
                
            yield batch
            
            count += len(batch)
            if limit and count >= limit:
                break
                
            last_id = batch[-1]['id']
