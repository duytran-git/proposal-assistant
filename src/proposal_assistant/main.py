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

    # Single handler for ALL message events — covers text-only, file uploads (modern
    # Files API V2 with no subtype), and legacy file_share subtype. Using @app.message()
    # alongside @app.event("message") causes Bolt to dispatch ambiguously: for no-subtype
    # file uploads, @app.message("Analyse") fires and returns early (no files guard), so
    # @app.event("message") may never fire, leaving the user with no response.
    @app.event("message")
    def handle_message_event(event, say, client):
        import sys

        logger = get_logger(__name__)
        subtype = event.get("subtype", "")
        text = event.get("text", "") or ""
        # Handle both modern (files list) and legacy (file singular) Slack event formats
        has_files = bool(event.get("files")) or bool(event.get("file"))

        print(
            f"[EVENT] subtype={subtype!r} text={text[:80]!r} has_files={has_files} "
            f"bot_id={event.get('bot_id')}",
            file=sys.stderr,
            flush=True,
        )

        # Skip bot messages to avoid self-triggering
        if event.get("bot_id") or subtype == "bot_message":
            print("[EVENT] Skipping bot message", file=sys.stderr, flush=True)
            return

        # Route on keyword — works for both text-only and file upload messages
        if "Analyse" in text:
            logger.info(
                "Routing to handle_analyse_command: subtype=%r has_files=%s", subtype, has_files
            )
            handle_analyse_command(event, say, client)
        elif "Propose" in text:
            logger.info(
                "Routing to handle_propose_command: subtype=%r has_files=%s", subtype, has_files
            )
            handle_propose_command(event, say, client)
        elif has_files:
            # File without a keyword = updated deal analysis upload
            logger.info("Routing file-only upload to handle_updated_deal_analysis")
            handle_updated_deal_analysis(event, say, client)
        # else: no keyword, no files — ignore silently

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
