from pathlib import Path

import markdown


INPUT_FILE = Path("output/newsletter.md")
OUTPUT_FILE = Path("output/newsletter.html")


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT_FILE}. Run the newsletter generator first."
        )

    markdown_content = INPUT_FILE.read_text(encoding="utf-8")

    html_content = markdown.markdown(
        markdown_content,
        extensions=[
            "extra",
            "sane_lists",
        ],
    )

    OUTPUT_FILE.write_text(html_content, encoding="utf-8")

    print(f"Created {OUTPUT_FILE}")


if __name__ == "__main__":
    main()