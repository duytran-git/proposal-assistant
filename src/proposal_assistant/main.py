"""Main entry point for Proposal Assistant Slack bot."""

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from proposal_assistant.config import get_config
from proposal_assistant.slack.handlers import (
    handle_analyse_command,
    handle_approval,
    handle_cloud_consent_no,
    handle_cloud_consent_yes,
    handle_propose_command,
    handle_regenerate,
    handle_rejection,
    handle_status_command,
    handle_updated_deal_analysis,
)
from proposal_assistant.utils.logging import get_logger, setup_logging


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

    # Register message handler for "Propose" command with file attachments
    @app.message("Propose")
    def propose_message(message, say, client):
        handle_propose_command(message, say, client)

    # Register message event listener for file uploads
    # This catches file_share messages (which have subtypes and skip @app.message)
    @app.event("message")
    def handle_message_event(event, say, client):
        logger = get_logger(__name__)
        subtype = event.get("subtype", "")
        text = event.get("text", "")
        has_files = bool(event.get("files"))
        logger.info(
            "Message event received: subtype=%r, text=%r, has_files=%s",
            subtype,
            text[:100] if text else "",
            has_files,
        )
        if event.get("files"):
            if "Analyse" in text:
                logger.info("Routing to handle_analyse_command")
                handle_analyse_command(event, say, client)
            elif "Propose" in text:
                logger.info("Routing to handle_propose_command")
                handle_propose_command(event, say, client)
            else:
                logger.info("Routing to handle_updated_deal_analysis")
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

    @app.action("regenerate_analysis")
    def regenerate_action(ack, body, say, client):
        ack()
        handle_regenerate(body, say, client)

    # Register action handlers for cloud consent buttons
    @app.action("cloud_consent_yes")
    def cloud_yes_action(ack, body, say, client):
        ack()
        handle_cloud_consent_yes(body, say, client)

    @app.action("cloud_consent_no")
    def cloud_no_action(ack, body, say, client):
        ack()
        handle_cloud_consent_no(body, say, client)

    # Register slash command for status check
    @app.command("/pa-status")
    def status_command(ack, respond):
        handle_status_command(ack, respond)

    return app


def main() -> None:
    """Run the bot in Socket Mode."""
    import sys

    config = get_config()

    # Configure structured logging with config log level
    setup_logging(config.log_level)
    logger = get_logger(__name__)

    # Ensure root proposal_assistant logger also outputs to stderr for Docker
    import logging

    root_pa_logger = logging.getLogger("proposal_assistant")
    if not any(isinstance(h, logging.StreamHandler) for h in root_pa_logger.handlers):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        root_pa_logger.addHandler(stderr_handler)

    app = create_app()

    logger.info("Starting Proposal Assistant bot in Socket Mode...")
    print("Proposal Assistant bot starting...", file=sys.stderr, flush=True)
    handler = SocketModeHandler(app, config.slack_app_token)
    handler.start()


if __name__ == "__main__":
    main()
