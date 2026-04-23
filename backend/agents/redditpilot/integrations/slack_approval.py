"""
RedditPilot Slack Integration
Approval workflow for content before posting.
Posts draft content to Slack with Approve/Edit/Reject buttons.
"""

import json
import logging
import requests
from typing import Optional
from ..core.config import Config, SlackConfig

logger = logging.getLogger("redditpilot.slack")


class SlackApproval:
    """Posts content drafts to Slack for human approval."""

    def __init__(self, config: Config):
        self.config = config
        self.slack = config.slack

    def request_comment_approval(self, comment_data: dict,
                                  post_data: dict, client_name: str) -> bool:
        """
        Post a comment draft to Slack for approval.
        Returns True if message was sent successfully.
        """
        if not self.slack.enabled or not self.slack.bot_token:
            logger.warning("Slack not configured, skipping approval")
            return False

        # Build the Block Kit message
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":speech_balloon: RedditPilot Comment Draft"}
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Client:* {client_name}"},
                    {"type": "mrkdwn", "text": f"*Subreddit:* r/{post_data.get('subreddit', '?')}"},
                    {"type": "mrkdwn", "text": f"*Tone:* {comment_data.get('tone', '?')}"},
                    {"type": "mrkdwn", "text": f"*AI Score:* {comment_data.get('validation', {}).get('ai_detection_score', '?'):.1f}/10"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Original Post:* <{post_data.get('permalink', '#')}|{post_data.get('title', 'Unknown')[:100]}>"}
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Draft Comment:*\n```{comment_data.get('content', '')[:2000]}```"}
            },
        ]

        # Add validation warnings if any
        validation = comment_data.get("validation", {})
        if validation.get("warnings"):
            warning_text = "\n".join([f":warning: {w}" for w in validation["warnings"]])
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Warnings:*\n{warning_text}"}
            })

        # Approval buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":white_check_mark: Approve"},
                    "style": "primary",
                    "action_id": "redditpilot_approve",
                    "value": json.dumps({
                        "action": "approve",
                        "comment_id": comment_data.get("db_id"),
                        "post_id": post_data.get("id"),
                    }),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":pencil2: Edit"},
                    "action_id": "redditpilot_edit",
                    "value": json.dumps({
                        "action": "edit",
                        "comment_id": comment_data.get("db_id"),
                    }),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":x: Reject"},
                    "style": "danger",
                    "action_id": "redditpilot_reject",
                    "value": json.dumps({
                        "action": "reject",
                        "comment_id": comment_data.get("db_id"),
                    }),
                },
            ]
        })

        return self._send_blocks(blocks)

    def request_post_approval(self, post_draft: dict, client_name: str) -> bool:
        """Post a new post draft to Slack for approval."""
        if not self.slack.enabled or not self.slack.bot_token:
            return False

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":memo: RedditPilot Post Draft"}
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Client:* {client_name}"},
                    {"type": "mrkdwn", "text": f"*Subreddit:* r/{post_draft.get('subreddit', '?')}"},
                    {"type": "mrkdwn", "text": f"*Type:* {post_draft.get('post_type', '?')}"},
                    {"type": "mrkdwn", "text": f"*Tone:* {post_draft.get('tone', '?')}"},
                ]
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Title:*\n{post_draft.get('title', '')}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Body:*\n```{post_draft.get('body', '')[:2000]}```"}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": ":white_check_mark: Approve"},
                        "style": "primary",
                        "action_id": "redditpilot_approve_post",
                        "value": json.dumps({"action": "approve", "post_id": post_draft.get("db_id")}),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": ":pencil2: Edit"},
                        "action_id": "redditpilot_edit_post",
                        "value": json.dumps({"action": "edit", "post_id": post_draft.get("db_id")}),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": ":x: Reject"},
                        "style": "danger",
                        "action_id": "redditpilot_reject_post",
                        "value": json.dumps({"action": "reject", "post_id": post_draft.get("db_id")}),
                    },
                ]
            }
        ]

        return self._send_blocks(blocks)

    def send_notification(self, message: str, blocks: list = None) -> bool:
        """Send a simple notification to the notification channel."""
        channel = self.slack.notification_channel or self.slack.approval_channel
        if not channel:
            return False

        if blocks:
            return self._send_blocks(blocks, channel=channel)

        return self._send_message(message, channel=channel)

    def send_performance_report(self, report: dict, client_name: str = "All Clients") -> bool:
        """Send a formatted performance report to Slack."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f":chart_with_upwards_trend: RedditPilot Report — {client_name}"}
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Comments Posted:* {report['comments']['total']}"},
                    {"type": "mrkdwn", "text": f"*Avg Comment Score:* {report['comments']['avg_score']}"},
                    {"type": "mrkdwn", "text": f"*Posts Created:* {report['posts']['total']}"},
                    {"type": "mrkdwn", "text": f"*Avg Post Score:* {report['posts']['avg_score']}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Removed Content:* {report['removed_content']} items"}
            },
        ]

        if report.get("top_subreddits"):
            sub_text = "\n".join([
                f"• r/{s['subreddit']}: {s['actions']} actions, avg score {s['avg_score']:.1f}"
                for s in report["top_subreddits"][:5]
            ])
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Top Subreddits:*\n{sub_text}"}
            })

        return self._send_blocks(blocks)

    def _send_blocks(self, blocks: list, channel: str = None) -> bool:
        """Send Block Kit message to Slack."""
        channel = channel or self.slack.approval_channel
        if not channel or not self.slack.bot_token:
            return False

        try:
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.slack.bot_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": channel,
                    "blocks": blocks,
                },
                timeout=10,
            )
            data = response.json()
            if not data.get("ok"):
                logger.error(f"Slack API error: {data.get('error')}")
                return False
            return True
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False

    def _send_message(self, text: str, channel: str = None) -> bool:
        """Send a simple text message to Slack."""
        channel = channel or self.slack.approval_channel
        if not channel or not self.slack.bot_token:
            return False

        try:
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.slack.bot_token}",
                    "Content-Type": "application/json",
                },
                json={"channel": channel, "text": text},
                timeout=10,
            )
            return response.json().get("ok", False)
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False
