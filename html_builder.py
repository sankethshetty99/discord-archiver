import os
import datetime
import markdown
from jinja2 import Environment, BaseLoader

class DiscordRenderer:
    """Renders Discord messages to HTML using a Jinja2 template with high fidelity."""
    
    TEMPLATE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Discord Archive - {{ channel_name }}</title>
        <style>
            @font-face {
                font-family: 'gg sans';
                font-weight: 400;
                src: local('gg sans'), local('Helvetica Neue'), local('Helvetica'), local('Arial'), sans-serif;
            }
            
            :root {
                --background-primary: #313338;
                --background-secondary: #2b2d31;
                --text-normal: #dbdee1;
                --text-muted: #949ba4;
                --header-primary: #f2f3f5;
                --interactive-active: #fff;
                --brand-experiment: #5865f2;
                --background-mentioned: rgba(250, 166, 26, 0.1);
                --background-mentioned-hover: rgba(250, 166, 26, 0.08);
                --info-warning-foreground: #f0b232;
            }

            body {
                background-color: var(--background-primary);
                color: var(--text-normal);
                font-family: 'gg sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 0;
                overflow-x: hidden;
            }

            a {
                color: #00a8fc;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }

            .chat-container {
                display: flex;
                flex-direction: column;
                padding: 16px;
                max-width: 100%;
            }

            .server-header {
                padding: 16px;
                border-bottom: 1px solid #26272d;
                margin-bottom: 16px;
            }
            .channel-hash {
                color: var(--text-muted);
                font-size: 24px;
                margin-right: 8px;
            }
            .channel-name {
                font-size: 24px;
                font-weight: 700;
                color: var(--header-primary);
            }
            .archive-meta {
                color: var(--text-muted);
                font-size: 14px;
                margin-top: 8px;
            }

            /* Message Group */
            .message-group {
                display: flex;
                margin-top: 17px;
                padding: 2px 16px;
                position: relative;
            }
            .message-group:hover {
                background-color: rgba(4, 4, 5, 0.07);
            }

            .avatar-column {
                width: 48px;
                margin-right: 16px;
                flex-shrink: 0;
            }
            .avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background-color: var(--brand-experiment);
                cursor: pointer;
                overflow: hidden;
            }
            .avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .content-column {
                flex: 1;
                min-width: 0;
            }

            /* Header (Username + Time) */
            .message-header {
                display: flex;
                align-items: center;
                margin-bottom: 2px;
            }
            .username {
                font-size: 16px;
                font-weight: 500;
                color: var(--header-primary);
                margin-right: 8px;
                cursor: pointer;
            }
            .username:hover {
                text-decoration: underline;
            }
            .timestamp {
                font-size: 12px;
                color: var(--text-muted);
                margin-left: 0.25rem;
            }
            .bot-tag {
                background-color: #5865f2;
                color: white;
                font-size: 10px;
                padding: 1px 4px;
                border-radius: 3px;
                margin-right: 8px;
                vertical-align: middle;
                display: inline-flex;
                align-items: center;
                height: 15px;
            }

            /* Message Content */
            .message-content {
                font-size: 16px;
                line-height: 1.375rem;
                color: var(--text-normal);
                white-space: pre-wrap;
                word-wrap: break-word;
            }

            /* Markdown Styles */
            .message-content strong { font-weight: 700; }
            .message-content em { font-style: italic; }
            .message-content code {
                font-family: Consolas, "Andale Mono WT", "Andale Mono", "Lucida Console", "Lucida Sans Typewriter", "DejaVu Sans Mono", "Bitstream Vera Sans Mono", "Liberation Mono", "Nimbus Mono L", Monaco, "Courier New", Courier, monospace;
                background-color: #2b2d31;
                padding: 2px;
                border-radius: 3px;
                font-size: 85%;
            }
            .message-content pre {
                background-color: #2b2d31;
                border: 1px solid #1e1f22;
                border-radius: 4px;
                padding: 8px;
                margin: 4px 0;
                max-width: 100%;
                overflow-x: auto;
            }
            .message-content pre code {
                background-color: transparent;
                padding: 0;
                font-size: 14px;
            }
            .message-content blockquote {
                display: flex;
                margin: 0;
                padding: 0 0 0 4px;
                border-left: 4px solid #4e5058;
                max-width: 100%;
            }
            .message-content blockquote > div {
                padding: 8px 12px;
                width: 100%;
            }

            /* Adjacent Matches (Simplified view for same user) */
            .message-adjacent {
                margin-top: 0;
                padding: 2px 16px; 
            }
            .message-adjacent:hover {
                background-color: rgba(4, 4, 5, 0.07);
            }
            .message-adjacent .avatar-column {
                display: none; /* Or specific hidden/timestamp on hover behavior */
            }
            .message-adjacent .content-column {
                margin-left: 64px; /* Align with previous content (48+16) */
            }

            /* Attachments & Embeds */
            .attachments-container {
                display: flex;
                flex-direction: column;
                gap: 8px;
                margin-top: 4px;
            }
            
            .attachment-item {
                border-radius: 3px;
                overflow: hidden;
            }
            .attachment-item img {
                max-width: 550px;
                max-height: 350px;
                border-radius: 8px;
                cursor: pointer;
            }
            
            .embed {
                display: grid;
                grid-template-columns: auto;
                grid-template-rows: auto;
                max-width: 520px;
                background-color: #2b2d31;
                border-radius: 4px;
                border-left: 4px solid #202225; /* Default color fallback */
                padding: 8px 16px 16px 12px;
                margin-top: 8px;
            }
            .embed-title {
                font-weight: 600;
                margin-bottom: 4px;
                display: inline-block;
            }
            .embed-description {
                font-size: 14px;
                color: var(--text-normal);
                white-space: pre-wrap;
            }
            .embed-footer {
                margin-top: 8px;
                font-size: 12px;
                color: var(--text-muted);
                display: flex;
                align-items: center;
            }
            .embed-image {
                margin-top: 16px;
                border-radius: 4px;
                overflow: hidden;
            }
            .embed-image img {
                max-width: 100%;
                border-radius: 4px;
            }

        </style>
    </head>
    <body>
        <div class="server-header">
            <div>
                <span class="channel-hash">#</span>
                <span class="channel-name">{{ channel_name }}</span>
            </div>
            <div class="archive-meta">Archive generated on {{ archive_date }}</div>
        </div>
        
        <div class="chat-container">
        {% for group in message_groups %}
            <div class="message-group">
                <div class="avatar-column">
                    <div class="avatar">
                        {% if group.avatar_url %}
                        <img src="{{ group.avatar_url }}" alt="{{ group.user }}" onerror="this.style.display='none'">
                        {% else %}
                        <!-- Fallback Letter -->
                        <div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:white; font-size:18px;">{{ group.user[0] | upper }}</div>
                        {% endif %}
                    </div>
                </div>
                
                <div class="content-column">
                    <div class="message-header">
                        <span class="username" {% if group.color %}style="color: {{ group.color }}"{% endif %}>{{ group.user }}</span>
                        {% if group.bot %}
                        <span class="bot-tag">BOT</span>
                        {% endif %}
                        <span class="timestamp">{{ group.timestamp }}</span>
                    </div>

                    {% for msg in group.messages %}
                        <div class="message-row" style="margin-top: 2px;">
                            {% if msg.content_html %}
                            <div class="message-content">{{ msg.content_html | safe }}</div>
                            {% endif %}
                            
                            <!-- Attachments -->
                            {% if msg.attachments %}
                            <div class="attachments-container">
                                {% for att in msg.attachments %}
                                    <div class="attachment-item">
                                        {% if 'image' in att.content_type %}
                                            <a href="{{ att.url }}" target="_blank"><img src="{{ att.url }}" alt="Image"></a>
                                        {% else %}
                                            <div style="background: #2b2d31; padding: 10px; border-radius: 4px; border: 1px solid #1e1f22; width: fit-content;">
                                                <a href="{{ att.url }} " target="_blank" style="display: flex; align-items: center;">
                                                    <span style="font-size: 24px; margin-right: 8px;">📄</span>
                                                    <span style="color: var(--text-normal); font-weight: 500;">{{ att.filename }}</span>
                                                </a>
                                            </div>
                                        {% endif %}
                                    </div>
                                {% endfor %}
                            </div>
                            {% endif %}
                            
                            <!-- Embeds -->
                            {% if msg.embeds %}
                                {% for embed in msg.embeds %}
                                <div class="embed" style="border-left-color: {{ embed.color_hex }};">
                                    <div class="embed-content">
                                        {% if embed.title %}
                                        <div class="embed-title"><a href="{{ embed.url }}" target="_blank" style="color: var(--header-primary);">{{ embed.title }}</a></div>
                                        {% endif %}
                                        
                                        {% if embed.description %}
                                        <div class="embed-description">{{ embed.description | safe }}</div>
                                        {% endif %}
                                        
                                        {% if embed.fields %}
                                            <div style="display: grid; gap: 8px; margin-top: 8px;">
                                            {% for field in embed.fields %}
                                                <div style="display: {% if field.inline %}inline-block{% else %}block{% endif %}; margin-right: 16px;">
                                                    <div style="font-weight: 600; color: var(--text-normal); font-size: 13px; margin-bottom: 2px;">{{ field.name }}</div>
                                                    <div style="font-size: 13px; color: var(--text-normal); white-space: pre-wrap;">{{ field.value }}</div>
                                                </div>
                                            {% endfor %}
                                            </div>
                                        {% endif %}
                                        
                                        {% if embed.image %}
                                        <div class="embed-image"><img src="{{ embed.image.url }}" alt="Embed Image"></div>
                                        {% endif %}
                                        
                                        {% if embed.footer %}
                                        <div class="embed-footer">
                                            {% if embed.footer.icon_url %}
                                            <img src="{{ embed.footer.icon_url }}" style="width: 20px; height: 20px; border-radius: 50%; margin-right: 8px;">
                                            {% endif %}
                                            {{ embed.footer.text }}
                                        </div>
                                        {% endif %}
                                    </div>
                                </div>
                                {% endfor %}
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>
            </div>
        {% endfor %}
        </div>
    </body>
    </html>
    """
    
    @staticmethod
    def render(channel_name, messages):
        """
        Render messages to HTML string.
        Expects messages in reverse chronological order (newest first).
        """
        # 1. Reverse to chronological
        msgs = list(reversed(messages))
        
        # 2. Group messages
        groups = []
        if not msgs: return ""
        
        current_group = None
        
        for m in msgs:
            user = m['author']['username']
            user_id = m['author']['id']
            avatar_hash = m['author'].get('avatar')
            bot = m['author'].get('bot', False)
            
            # Construct Avatar URL
            if avatar_hash:
                # Basic avatar extension logic
                ext = 'gif' if avatar_hash.startswith('a_') else 'png'
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=64"
            else:
                # Default avatar logic (modulo 5)
                discriminator = int(m['author'].get('discriminator', '0'))
                if discriminator == 0:
                     # New username system: (user_id >> 22) % 6
                     default_idx = (int(user_id) >> 22) % 6
                else:
                     default_idx = discriminator % 5
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_idx}.png"

            # Parse timestamp safely
            try:
                ts_dt = datetime.datetime.fromisoformat(m['timestamp'])
                ts_str = ts_dt.strftime("%Y-%m-%d %H:%M")
            except:
                ts_str = m['timestamp']
            
            # Markdown processing
            content_raw = m.get('content', '')
            # Use Python-Markdown to convert to HTML
            # We enable 'fenced_code' and 'nl2br' for better Discord parity
            content_html = markdown.markdown(content_raw, extensions=['fenced_code', 'nl2br'])
            
            # Embed Processing (Simplify color)
            processed_embeds = []
            if 'embeds' in m:
                for e in m['embeds']:
                    # Convert color int to hex
                    c_val = e.get('color', 0x202225)
                    if c_val:
                        e['color_hex'] = f"#{c_val:06x}"
                    else:
                        e['color_hex'] = "#202225"
                        
                    # Parse description markdown
                    if 'description' in e:
                        e['description'] = markdown.markdown(e['description'], extensions=['nl2br'])
                        
                    processed_embeds.append(e)

            # Start new group if user changes or enough time passes (e.g. 5 mins - simplified here to just user check for now)
            # Or if the previous message was too long ago
            
            if not current_group or current_group['user'] != user:
                current_group = {
                    'user': user,
                    'is_bot': bot,
                    'timestamp': ts_str,
                    'avatar_url': avatar_url,
                    'messages': []
                }
                groups.append(current_group)
            
            current_group['messages'].append({
                'content_html': content_html,
                'attachments': m.get('attachments', []),
                'embeds': processed_embeds
            })
            
        env = Environment(loader=BaseLoader())
        template = env.from_string(DiscordRenderer.TEMPLATE)
        
        return template.render(
            channel_name=channel_name,
            archive_date=datetime.datetime.now().strftime("%Y-%m-%d"),
            message_groups=groups
        )
