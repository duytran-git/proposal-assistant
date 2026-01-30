"""Main entry point for Proposal Assistant Slack bot."""

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from proposal_assistant.config import get_config
from proposal_assistant.slack.handlers import (
    handle_analyse_command,
    handle_approval,
    handle_cloud_consent_no,
    handle_cloud_consent_yes,
    handle_rejection,
    handle_updated_deal_analysis,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> App:
    """Create and configure the Slack Bolt app."""
    config = get_config()

    app = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
    )

    # Register message handler for "Analyse" command with file attachments
    @app.message("Analyse")
    def analyse_message(message, say, client):
        handle_analyse_command(message, say, client)

    # Register message event listener for file uploads in existing threads
    # This catches all messages and filters for file uploads in WAITING_FOR_APPROVAL
    @app.event("message")
    def handle_message_event(event, say, client):
        if event.get("files"):
            handle_updated_deal_analysis(event, say, client)

    # Register action handlers for approval buttons
    @app.action("approve_deck")
    def approve_action(ack, body, say, client):
        ack()
        handle_approval(body, say, client)

    @app.action("reject_deck")
    def reject_action(ack, body, say, client):
        ack()
        handle_rejection(body, say, client)

    # Register action handlers for cloud consent buttons
    @app.action("cloud_consent_yes")
    def cloud_yes_action(ack, body, say, client):
        ack()
        handle_cloud_consent_yes(body, say, client)

    @app.action("cloud_consent_no")
    def cloud_no_action(ack, body, say, client):
        ack()
        handle_cloud_consent_no(body, say, client)

    return app


def main() -> None:
    """Run the bot in Socket Mode."""
    config = get_config()
    app = create_app()

    logger.info("Starting Proposal Assistant bot in Socket Mode...")
    handler = SocketModeHandler(app, config.slack_app_token)
    handler.start()


if __name__ == "__main__":
    main()
