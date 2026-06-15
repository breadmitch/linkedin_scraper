from pathlib import Path
from datetime import datetime
import json
import re


def safe_filename(text: str) -> str:
    text = text.strip() or "linkedin_profile"
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80]


def model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def profile_to_markdown(person_data: dict) -> str:
    name = person_data.get("name") or "Unknown Profile"
    location = person_data.get("location") or ""
    about = person_data.get("about") or ""
    linkedin_url = person_data.get("linkedin_url") or ""
    open_to_work = person_data.get("open_to_work", False)

    experiences = person_data.get("experiences") or []
    educations = person_data.get("educations") or []
    interests = person_data.get("interests") or []
    accomplishments = person_data.get("accomplishments") or []
    contacts = person_data.get("contacts") or []

    created = datetime.now().strftime("%Y-%m-%d %H:%M")

    md = f"""---
name: "{name}"
location: "{location}"
linkedin_url: "{linkedin_url}"
open_to_work: {open_to_work}
created: "{created}"
tags:
  - linkedin
  - profile
---

# {name}

## Location

{location or "_No location found._"}

## LinkedIn URL

{linkedin_url or "_No URL found._"}

## Open To Work

{open_to_work}

## About

{about or "_No about section found._"}

## Experience

"""

    if experiences:
        for exp in experiences:
            title = exp.get("position_title") or "Untitled role"
            company = exp.get("institution_name") or ""
            from_date = exp.get("from_date") or ""
            to_date = exp.get("to_date") or ""
            duration = exp.get("duration") or ""
            exp_location = exp.get("location") or ""
            description = exp.get("description") or ""
            exp_url = exp.get("linkedin_url") or ""

            md += f"### {title}\n\n"
            if company:
                md += f"**Company:** {company}\n\n"
            if from_date or to_date:
                md += f"**Dates:** {from_date} - {to_date}\n\n"
            if duration:
                md += f"**Duration:** {duration}\n\n"
            if exp_location:
                md += f"**Location:** {exp_location}\n\n"
            if exp_url:
                md += f"**LinkedIn:** {exp_url}\n\n"
            if description:
                md += f"{description}\n\n"
    else:
        md += "_No experience found._\n\n"

    md += "## Education\n\n"

    if educations:
        for edu in educations:
            school = edu.get("institution_name") or "Unknown school"
            degree = edu.get("degree") or ""
            from_date = edu.get("from_date") or ""
            to_date = edu.get("to_date") or ""
            description = edu.get("description") or ""
            edu_url = edu.get("linkedin_url") or ""

            md += f"### {school}\n\n"
            if degree:
                md += f"**Degree:** {degree}\n\n"
            if from_date or to_date:
                md += f"**Dates:** {from_date} - {to_date}\n\n"
            if edu_url:
                md += f"**LinkedIn:** {edu_url}\n\n"
            if description:
                md += f"{description}\n\n"
    else:
        md += "_No education found._\n\n"

    md += "## Interests\n\n"

    if interests:
        for interest in interests:
            interest_name = interest.get("name") or ""
            category = interest.get("category") or ""
            url = interest.get("linkedin_url") or ""

            md += f"- {interest_name}"
            if category:
                md += f" ({category})"
            if url:
                md += f" — {url}"
            md += "\n"
    else:
        md += "_No interests found._\n"

    md += "\n## Accomplishments\n\n"

    if accomplishments:
        for acc in accomplishments:
            title = acc.get("title") or "Untitled accomplishment"
            category = acc.get("category") or ""
            issuer = acc.get("issuer") or ""
            issued_date = acc.get("issued_date") or ""
            description = acc.get("description") or ""

            md += f"### {title}\n\n"
            if category:
                md += f"**Category:** {category}\n\n"
            if issuer:
                md += f"**Issuer:** {issuer}\n\n"
            if issued_date:
                md += f"**Issued:** {issued_date}\n\n"
            if description:
                md += f"{description}\n\n"
    else:
        md += "_No accomplishments found._\n"

    md += "\n## Contacts\n\n"

    if contacts:
        for contact in contacts:
            contact_type = contact.get("type") or "contact"
            value = contact.get("value") or ""
            label = contact.get("label") or ""

            md += f"- **{contact_type}:** {value}"
            if label:
                md += f" ({label})"
            md += "\n"
    else:
        md += "_No contacts found._\n"

    return md


def save_profile_outputs(person_data: dict, output_dir: str):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    name = person_data.get("name") or "linkedin_profile"
    base_name = safe_filename(name)

    json_path = output_path / f"{base_name}.json"
    md_path = output_path / f"{base_name}.md"

    json_path.write_text(
        json.dumps(person_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_path.write_text(
        profile_to_markdown(person_data),
        encoding="utf-8",
    )

    return md_path, json_path

