import os
import datetime
from jinja2 import Environment, BaseLoader

class DiscordRenderer:
    """Renders Discord messages to HTML using a Jinja2 template."""
    
    TEMPLATE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            body {
                background-color: #313338;
                color: #dbdee1;
                font-family: 'gg sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 20px;
            }
            .message-group {
                margin: 10px 0;
                padding: 2px 0;
            }
            .header {
                display: flex;
                align-items: center;
                margin-bottom: 4px;
            }
            .avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                margin-right: 16px;
                background-color: #5865f2; /* Default blurple */
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 14px;
                color: white;
            }
            .username {
                font-weight: 500;
                color: #f2f3f5;
                font-size: 16px;
                margin-right: 8px;
            }
            .timestamp {
                color: #949ba4;
                font-size: 12px;
            }
            .content {
                margin-left: 56px;
                white-space: pre-wrap;
                font-size: 16px;
                line-height: 1.375rem;
            }
            .attachment {
                margin-left: 56px;
                margin-top: 8px;
                max-width: 400px;
            }
            .attachment img {
                max-width: 100%;
                border-radius: 8px;
            }
            .server-header {
                border-bottom: 1px solid #3f4147;
                padding-bottom: 20px;
                margin-bottom: 20px;
            }
            .channel-name {
                font-size: 24px;
                font-weight: bold;
                color: #f2f3f5;
            }
        </style>
    </head>
    <body>
        <div class="server-header">
            <div class="channel-name"># {{ channel_name }}</div>
            <div class="timestamp">Archived on {{ archive_date }}</div>
        </div>
        
        {% for group in message_groups %}
        <div class="message-group">
            <div class="header">
                <div class="avatar">{{ group.user[0] | upper }}</div>
                <span class="username">{{ group.user }}</span>
                <span class="timestamp">{{ group.timestamp }}</span>
            </div>
            {% for msg in group.messages %}
                {% if msg.content %}
                <div class="content">{{ msg.content }}</div>
                {% endif %}
                
                {% for att in msg.attachments %}
                    <div class="attachment">
                        {% if att.content_type and 'image' in att.content_type %}
                            <img src="{{ att.url }}" alt="Attachment">
                        {% else %}
                            <a href="{{ att.url }}" style="color: #00a8fc;">{{ att.filename }}</a>
                        {% endif %}
                    </div>
                {% endfor %}
            {% endfor %}
        </div>
        {% endfor %}
    </body>
    </html>
    """
    
    @staticmethod
    def render(channel_name, messages):
        """
        Render messages to HTML string.
        Expects messages in reverse chronological order (newest first) from API,
        so it reverses them to chronological order.
        """
        # 1. Reverse to chronological
        msgs = list(reversed(messages))
        
        # 2. Group messages by user/time to mimic Discord UI compacting
        groups = []
        if not msgs: return ""
        
        current_group = None
        
        for m in msgs:
            user = m['author']['username']
            # Parse timestamp safely
            try:
                ts_dt = datetime.datetime.fromisoformat(m['timestamp'])
                ts_str = ts_dt.strftime("%Y-%m-%d %H:%M")
            except:
                ts_str = m['timestamp']
            
            # Start new group if user changes or enough time passes
            if not current_group or current_group['user'] != user:
                current_group = {
                    'user': user,
                    'timestamp': ts_str,
                    'messages': []
                }
                groups.append(current_group)
            
            current_group['messages'].append({
                'content': m.get('content', ''),
                'attachments': m.get('attachments', [])
            })
            
        env = Environment(loader=BaseLoader())
        template = env.from_string(DiscordRenderer.TEMPLATE)
        
        return template.render(
            channel_name=channel_name,
            archive_date=datetime.datetime.now().strftime("%Y-%m-%d"),
            message_groups=groups
        )
