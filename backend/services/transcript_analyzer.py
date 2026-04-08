"""Transcript-based AI analysis for Creator Quality Index.

Fetches YouTube transcripts and evaluates channel quality on 4 criteria
(research_depth, signal_noise, originality, lasting_impact) using AI.
Production quality cannot be evaluated from text transcripts.
"""
import json
import logging
import subprocess

from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

# Max chars to send for analysis (fits comfortably in context)
MAX_TRANSCRIPT_CHARS = 12000

ANALYSIS_PROMPT = """You are an expert YouTube content quality evaluator. Analyze this transcript and score it on 4 criteria (1-10 each).

**Channel**: {channel_name}
**Video**: "{video_title}"

## Scoring Rubrics

### Research Depth
- 9-10: Primary sources, academic papers, expert interviews, original data/proofs
- 7-8: Multiple credible sources, fact-checked, deep subject knowledge
- 5-6: Decent research, relies on secondary sources or surface-level analysis
- 3-4: Minimal sourcing, anecdotal evidence, occasional errors
- 1-2: No sources, speculation as fact

### Signal-to-Noise Ratio
- 9-10: Pure content, no filler, every second adds value
- 7-8: Minimal filler, brief sponsor reads, content-focused
- 5-6: Some padding but acceptable, occasional tangents
- 3-4: Significant filler, clickbait, artificial drama
- 1-2: More filler than content

### Originality
- 9-10: Invented a format, unique framework, genuinely novel approach
- 7-8: Distinct voice, recognizable style, original takes
- 5-6: Competent execution of established format
- 3-4: Derivative, follows trends
- 1-2: Pure repackaging

### Lasting Impact
- 9-10: Timeless content, fundamentally shifts understanding
- 7-8: Mostly evergreen, referenced years later
- 5-6: Good content with some time-sensitivity
- 3-4: Largely time-bound
- 1-2: Disposable content

## Transcript
{transcript}

## Instructions
Return ONLY a JSON object (no markdown, no commentary):
{{"research_depth": X, "signal_noise": X, "originality": X, "lasting_impact": X, "reasoning": {{"research_depth": "...", "signal_noise": "...", "originality": "...", "lasting_impact": "..."}}}}
"""


def fetch_transcript(video_id, languages=None):
    """Fetch transcript for a YouTube video.

    Args:
        video_id: YouTube video ID (not full URL).
        languages: Priority list of language codes. Defaults to ["en"].

    Returns:
        Full transcript text, or None if unavailable.
    """
    if languages is None:
        languages = ["en"]
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id, languages=languages)
        return " ".join(snippet.text for snippet in transcript)
    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        return None


def get_recent_video_id(channel_url):
    """Get the most recent video ID from a channel using yt-dlp.

    Args:
        channel_url: Full YouTube channel URL (e.g. https://www.youtube.com/@name).

    Returns:
        Video ID string, or None on failure.
    """
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--flat-playlist", "--playlist-end", "3",
                "--print", "%(id)s", f"{channel_url}/videos",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("yt-dlp failed for %s: %s", channel_url, e)
    return None


def get_video_title(video_id):
    """Get video title via yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "%(title)s", "--no-download", f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "Unknown"


def parse_ai_response(response_text):
    """Extract JSON scores from AI response text.

    Args:
        response_text: Raw text response from AI analysis.

    Returns:
        Dict with scores, or None if parsing fails.
    """
    # Try direct JSON parse
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        # Validate expected keys
        required = {"research_depth", "signal_noise", "originality", "lasting_impact"}
        if required.issubset(data.keys()):
            for key in required:
                val = data[key]
                if not isinstance(val, (int, float)) or val < 1 or val > 10:
                    logger.error("Invalid score for %s: %s", key, val)
                    return None
            return data
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.error("Failed to parse AI response: %s", e)
    return None


def analyze_channel(channel_name, channel_url, languages=None):
    """Fetch transcript and return analysis-ready data for a channel.

    This prepares everything needed for AI analysis but does NOT call AI itself
    (that's done via Task tool agents at the CLI/script level).

    Args:
        channel_name: Display name of the channel.
        channel_url: YouTube channel URL.
        languages: Language priority list.

    Returns:
        Dict with channel_name, video_id, video_title, transcript, prompt.
        Or None if transcript fetch fails.
    """
    video_id = get_recent_video_id(channel_url)
    if not video_id:
        logger.warning("No video found for %s", channel_name)
        return None

    transcript = fetch_transcript(video_id, languages)
    if not transcript:
        logger.warning("No transcript for %s (video %s)", channel_name, video_id)
        return None

    video_title = get_video_title(video_id)
    truncated = transcript[:MAX_TRANSCRIPT_CHARS]

    prompt = ANALYSIS_PROMPT.format(
        channel_name=channel_name,
        video_title=video_title,
        transcript=truncated,
    )

    return {
        "channel_name": channel_name,
        "video_id": video_id,
        "video_title": video_title,
        "transcript_length": len(transcript),
        "prompt": prompt,
    }


def compare_scores(manual_scores, ai_scores):
    """Compare manual vs AI scores and compute deltas.

    Args:
        manual_scores: Dict with score_research_depth, score_signal_noise, etc.
        ai_scores: Dict with research_depth, signal_noise, etc.

    Returns:
        Dict with per-criterion comparison and summary stats.
    """
    criteria_map = {
        "research_depth": "score_research_depth",
        "signal_noise": "score_signal_noise",
        "originality": "score_originality",
        "lasting_impact": "score_lasting_impact",
    }

    comparisons = {}
    total_delta = 0
    count = 0

    for ai_key, manual_key in criteria_map.items():
        manual_val = manual_scores.get(manual_key)
        ai_val = ai_scores.get(ai_key)
        if manual_val is not None and ai_val is not None:
            delta = ai_val - manual_val
            comparisons[ai_key] = {
                "manual": manual_val,
                "ai": ai_val,
                "delta": delta,
            }
            total_delta += abs(delta)
            count += 1

    return {
        "criteria": comparisons,
        "avg_absolute_delta": round(total_delta / count, 2) if count else None,
        "count": count,
    }
