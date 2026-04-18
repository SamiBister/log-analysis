#!/usr/bin/env python3
"""
Publish Markdown files from a directory to Confluence Cloud.
Preserves folder structure as page hierarchy.
"""

import os
import sys
from pathlib import Path

import markdown
from atlassian import Confluence


def prefixed(title, prefix):
    """Prepend prefix to a page title, or return the title unchanged if prefix is empty."""
    return f"{prefix}{title}" if prefix else title


def folder_page_title(docs_dir, folder_path):
    """
    Derive a space-unique Confluence page title for a folder.

    Confluence titles must be unique across the whole space, so we use the full
    relative path rather than just the leaf name.  Each path part has its numeric
    prefix stripped and is title-cased, then parts are joined with ' / '.

    Examples:
        docs/adr          -> "Adr"
        docs/poc/adr      -> "Poc / Adr"
        docs/00-intro     -> "Intro"
        docs/poc/00-intro -> "Poc / Intro"
    """
    rel = folder_path.relative_to(docs_dir)
    parts = []
    for part in rel.parts:
        if part and part[0].isdigit() and "-" in part:
            part = part.split("-", 1)[1]
        parts.append(part.replace("-", " ").title())
    return " / ".join(parts)


def get_or_create_folder_page(
    conf,
    space_key,
    folder_path,
    parent_id,
    folder_pages,
    docs_dir,
    confluence_prefix="",
):
    """Get or create a page for a folder"""
    folder_key = str(folder_path)
    if folder_key in folder_pages:
        return folder_pages[folder_key]

    title = prefixed(folder_page_title(docs_dir, folder_path), confluence_prefix)

    # Search for existing page among parent's children
    try:
        children = conf.get_page_child_by_type(
            parent_id, type="page", start=0, limit=100
        )
        for child in children:
            if child["title"] == title:
                print(f"  ✓ Found folder page: {title} (id: {child['id']})")
                folder_pages[folder_key] = child["id"]
                return child["id"]
    except Exception as e:
        print(f"  Warning: Could not check children: {e}")

    # Create folder page if not found
    print(f"  Creating folder page: {title} (under parent: {parent_id})")
    folder_page = conf.create_page(
        space=space_key,
        title=title,
        body=f"<p>This section contains documentation for {title}.</p>",
        parent_id=parent_id,
    )
    folder_pages[folder_key] = folder_page["id"]
    return folder_page["id"]


def get_nested_parent_id(
    conf,
    space_key,
    rel_path,
    docs_dir,
    root_page_id,
    folder_pages,
    confluence_prefix="",
):
    """Get parent page ID for nested folder structure"""
    if rel_path.parent == Path("."):
        # Top-level file -> child of root page
        return root_page_id

    # Build parent hierarchy from root to immediate parent
    parent_parts = rel_path.parent.parts
    current_parent_id = root_page_id

    # Create each folder level
    for i, part in enumerate(parent_parts):
        folder_path = docs_dir / Path(*parent_parts[: i + 1])
        current_parent_id = get_or_create_folder_page(
            conf,
            space_key,
            folder_path,
            current_parent_id,
            folder_pages,
            docs_dir,
            confluence_prefix,
        )

    return current_parent_id


def publish_docs(
    confluence_url,
    confluence_user,
    confluence_token,
    space_key,
    docs_path,
    root_page_title,
    confluence_prefix="",
):
    """Publish all markdown files to Confluence"""

    # Initialize Confluence client
    conf = Confluence(
        url=confluence_url,
        username=confluence_user,
        password=confluence_token,
        cloud=True,
    )

    # Get or create root page
    root_page_title_prefixed = prefixed(root_page_title, confluence_prefix)
    print(f"Setting up root page: {root_page_title_prefixed}")
    root_page = conf.get_page_by_title(space=space_key, title=root_page_title_prefixed)
    if root_page:
        print(f"✓ Found root page: {root_page_title_prefixed}")
        root_page_id = root_page["id"]
    else:
        # Create root page
        print(f"Creating root page: {root_page_title_prefixed}")
        root_page = conf.create_page(
            space=space_key,
            title=root_page_title_prefixed,
            body="<p>This is the root documentation page. Content is auto-generated from GitHub.</p>",
        )
        if not root_page:
            raise RuntimeError(
                f"Failed to create root page: {root_page_title_prefixed}"
            )
        print(f"✓ Created root page: {root_page_title_prefixed}")
        root_page_id = root_page["id"]

    # Cache for folder pages
    folder_pages = {}

    # Collect all markdown files
    docs_dir = Path(docs_path)
    md_files = list(docs_dir.rglob("*.md"))

    # Sort files: index.md first, then by depth, then alphabetically
    def sort_key(p):
        is_index = p.name == "index.md"
        depth = len(p.parts)
        return (not is_index, depth, str(p))

    md_files.sort(key=sort_key)

    print(f"\nPublishing {len(md_files)} files...\n")

    # Publish all markdown files
    for md_file in md_files:
        # Skip templates
        if "template" in md_file.name.lower():
            print(f"Skipping template: {md_file.relative_to(docs_dir)}")
            continue

        # Get relative path from docs/
        rel_path = md_file.relative_to(docs_dir)

        print(f"\nPublishing {rel_path}...")
        print(f"  File path: {md_file}")
        print(f"  Relative path: {rel_path}")
        print(f"  Parent: {rel_path.parent}")
        print(f"  Parent parts: {rel_path.parent.parts}")

        # Read markdown
        with open(md_file, "r", encoding="utf-8") as f:
            md_content = f.read()

        # Extract title from first # heading or use filename
        if md_content.startswith("# "):
            title = md_content.split("\n")[0].strip("# ")
        else:
            # Generate title from filename
            title = md_file.stem.replace("-", " ").title()

        # For index.md files, prefix with folder name to avoid conflicts
        if md_file.name == "index.md" and rel_path.parent != Path("."):
            folder_name = rel_path.parent.name
            # Remove number prefix from folder name
            if folder_name and folder_name[0].isdigit() and "-" in folder_name:
                folder_name = folder_name.split("-", 1)[1]
            folder_display = folder_name.replace("-", " ").title()
            # Only prefix if title is generic
            if title.lower() in ["index", "readme"]:
                title = f"{folder_display} - Overview"

        # Apply confluence prefix to the final title
        title = prefixed(title, confluence_prefix)

        # Convert to HTML
        html_content = markdown.markdown(
            md_content, extensions=["tables", "fenced_code"]
        )

        # Determine parent page ID based on folder structure (supports nested folders)
        parent_id = get_nested_parent_id(
            conf,
            space_key,
            rel_path,
            docs_dir,
            root_page_id,
            folder_pages,
            confluence_prefix,
        )

        # Check if page exists
        existing = conf.get_page_by_title(space=space_key, title=title)

        if existing:
            # Update existing page
            conf.update_page(
                page_id=existing["id"],
                title=title,
                body=html_content,
                parent_id=parent_id,
            )
            print(f"  ✓ Updated: {title}")
        else:
            # Create new page
            conf.create_page(
                space=space_key, title=title, body=html_content, parent_id=parent_id
            )
            print(f"  ✓ Created: {title}")

    print("\n✓ All pages published successfully!")


if __name__ == "__main__":
    # Get configuration from environment variables
    confluence_url = os.environ.get("CONFLUENCE_URL")
    confluence_user = os.environ.get("CONFLUENCE_USER")
    confluence_token = os.environ.get("CONFLUENCE_API_TOKEN")
    space_key = os.environ.get("CONFLUENCE_SPACE_KEY")
    docs_path = os.environ.get("DOCS_PATH", "docs")
    root_page_title = os.environ.get("ROOT_PAGE_TITLE", "Documentation")
    confluence_prefix = os.environ.get("CONFLUENCE_PREFIX", "")

    # Validate required inputs
    if not all([confluence_url, confluence_user, confluence_token, space_key]):
        print("Error: Missing required environment variables")
        print(
            "Required: CONFLUENCE_URL, CONFLUENCE_USER, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEY"
        )
        sys.exit(1)

    try:
        publish_docs(
            confluence_url=confluence_url,
            confluence_user=confluence_user,
            confluence_token=confluence_token,
            space_key=space_key,
            docs_path=docs_path,
            root_page_title=root_page_title,
            confluence_prefix=confluence_prefix,
        )
    except Exception as e:
        print(
            f"\n✗ Error: {type(e).__name__}: {e.args[0] if e.args else 'unknown error'}"
        )
        sys.exit(1)
