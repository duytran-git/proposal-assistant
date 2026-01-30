"""Unit tests for multi-file transcript merging."""

from proposal_assistant.llm.context_builder import ContextBuilder


class TestTwoFilesMerged:
    """Tests for merging exactly two transcript files."""

    def test_two_files_have_numbered_markers(self):
        """Two transcripts get Transcript 1 and Transcript 2 markers."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "First meeting content",
                "Second meeting content",
            ]
        )

        assert "--- Transcript 1 ---" in result.context
        assert "--- Transcript 2 ---" in result.context

    def test_two_files_content_preserved(self):
        """Both transcript contents are fully included."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "Alpha discussion notes",
                "Beta discussion notes",
            ]
        )

        assert "Alpha discussion notes" in result.context
        assert "Beta discussion notes" in result.context

    def test_two_files_separated_by_newlines(self):
        """Transcripts are separated by blank lines."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "Content A",
                "Content B",
            ]
        )

        # Each marker followed by double newline, then content
        assert "--- Transcript 1 ---\n\nContent A" in result.context
        assert "--- Transcript 2 ---\n\nContent B" in result.context


class TestThreeFilesMerged:
    """Tests for merging three transcript files."""

    def test_three_files_have_all_markers(self):
        """Three transcripts get markers 1, 2, and 3."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "Meeting one",
                "Meeting two",
                "Meeting three",
            ]
        )

        assert "--- Transcript 1 ---" in result.context
        assert "--- Transcript 2 ---" in result.context
        assert "--- Transcript 3 ---" in result.context

    def test_three_files_all_content_included(self):
        """All three transcript contents are included."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "January meeting notes",
                "February meeting notes",
                "March meeting notes",
            ]
        )

        assert "January meeting notes" in result.context
        assert "February meeting notes" in result.context
        assert "March meeting notes" in result.context


class TestOrderPreserved:
    """Tests that transcript order is preserved during merging."""

    def test_markers_in_sequential_order(self):
        """Transcript markers appear in 1, 2, 3 order."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "First",
                "Second",
                "Third",
            ]
        )

        context = result.context
        pos1 = context.find("--- Transcript 1 ---")
        pos2 = context.find("--- Transcript 2 ---")
        pos3 = context.find("--- Transcript 3 ---")

        assert pos1 < pos2 < pos3

    def test_content_follows_corresponding_marker(self):
        """Each content block follows its marker."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "ALPHA_CONTENT",
                "BETA_CONTENT",
                "GAMMA_CONTENT",
            ]
        )

        context = result.context

        # Find marker and content positions
        marker1 = context.find("--- Transcript 1 ---")
        content1 = context.find("ALPHA_CONTENT")
        marker2 = context.find("--- Transcript 2 ---")
        content2 = context.find("BETA_CONTENT")
        marker3 = context.find("--- Transcript 3 ---")
        content3 = context.find("GAMMA_CONTENT")

        # Each content must come after its marker but before the next marker
        assert marker1 < content1 < marker2
        assert marker2 < content2 < marker3
        assert marker3 < content3

    def test_original_order_maintained(self):
        """Files provided in order [A, B, C] appear as [A, B, C]."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "FILE_A_UNIQUE_MARKER",
                "FILE_B_UNIQUE_MARKER",
                "FILE_C_UNIQUE_MARKER",
            ]
        )

        context = result.context
        pos_a = context.find("FILE_A_UNIQUE_MARKER")
        pos_b = context.find("FILE_B_UNIQUE_MARKER")
        pos_c = context.find("FILE_C_UNIQUE_MARKER")

        assert pos_a < pos_b < pos_c, "Files should maintain original order"

    def test_four_files_order_preserved(self):
        """Four files maintain order."""
        builder = ContextBuilder()
        result = builder.build_context(
            [
                "Meeting 1: Kickoff",
                "Meeting 2: Design",
                "Meeting 3: Review",
                "Meeting 4: Signoff",
            ]
        )

        context = result.context
        assert context.find("Kickoff") < context.find("Design")
        assert context.find("Design") < context.find("Review")
        assert context.find("Review") < context.find("Signoff")
