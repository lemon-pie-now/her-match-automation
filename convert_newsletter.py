from pathlib import Path
import re

import markdown


INPUT_FILE = Path("output/newsletter.md")
OUTPUT_FILE = Path("output/newsletter.html")
NEWSLETTER_HEADING = (
    '<h2 class="hynlcx1 hynlcx3">'
    '<span class="hxnnnr0"><strong>Upcoming Matches</strong></span>'
    "</h2>"
)


def add_event_markup(markdown_content: str) -> str:
    """Group matches by day and add visual time and location markers."""
    marked_up_lines: list[str] = []
    pending_title: str | None = None
    current_date: str | None = None

    for line in markdown_content.splitlines():
        if line.startswith("## "):
            current_date = None
            marked_up_lines.append(line)

        elif line.startswith("### "):
            title = line.removeprefix("### ")
            title = title.removeprefix("⚽️").removeprefix("⚽").lstrip()
            pending_title = title
        elif line.count(" | ") == 2:
            date, event_time, location = line.split(" | ", maxsplit=2)
            if date != current_date:
                if current_date is not None:
                    marked_up_lines.extend(
                        [
                            "",
                            (
                               "" '<div class="_7pt7ks10">'
                               "" '<div class="_7pt7ks1"></div>'
                                "</div>"
                            ),
                        ]
                    )
                marked_up_lines.extend(["", f"### {date}", ""])
                current_date = date

            if pending_title is not None:
                marked_up_lines.extend([f"#### {pending_title}", ""])
                pending_title = None

            """marked_up_lines.append(
                f"🕒 {event_time} | 📍 {location}"
            )
"""
        else:
            marked_up_lines.append(line)

    return "\n".join(marked_up_lines)


def add_html_markup(html_content: str) -> str:
    """Apply the newsletter editor's classes and nested text markup."""
    html_content = re.sub(
        r"<h3>(.*?)</h3>",
        (
            '<h3 class="hynlcx1 hynlcx4">'
            r'<span class="hxnnnr0"><strong>\1</strong></span></h3>'
        ),
        html_content,
    )
    html_content = re.sub(
        r"<h4>(.*?)</h4>",
        (
            '<p class="dream-post-content-paragraph j6zgbu1">'
            r'<span class="hxnnnr0"><strong>\1</strong></span></p>'
        ),
        html_content,
    )
    html_content = re.sub(
        r"<p>(🕒 .*? \| 📍 .*?)</p>",
        (
            '<p class="dream-post-content-paragraph j6zgbu1">'
            r'<span class="hxnnnr0">\1</span></p>'
        ),
        html_content,
    )
    return html_content


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT_FILE}. Run the newsletter generator first."
        )

    markdown_content = add_event_markup(
        INPUT_FILE.read_text(encoding="utf-8")
    )

    html_content = markdown.markdown(
        markdown_content,
        extensions=[
            "extra",
            "sane_lists",
        ],
    )
    html_content = add_html_markup(html_content)
    html_content = f"{NEWSLETTER_HEADING}\n{html_content}"

    OUTPUT_FILE.write_text(html_content, encoding="utf-8")

    print(f"Created {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
