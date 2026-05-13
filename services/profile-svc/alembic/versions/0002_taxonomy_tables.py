"""0002 — vocation_taxonomy and personality_questions tables + seed data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# 9-category vocation taxonomy seed (plan §4)
# ---------------------------------------------------------------------------

TAXONOMY_SEED = [
    # V1. Visual Arts
    ("Visual Arts", "illustration", "Illustration"),
    ("Visual Arts", "painting", "Painting"),
    ("Visual Arts", "mixed-media", "Mixed Media"),
    ("Visual Arts", "oil-painting", "Oil Painting"),
    ("Visual Arts", "watercolor", "Watercolor"),
    ("Visual Arts", "acrylic", "Acrylic"),
    ("Visual Arts", "gouache", "Gouache"),
    ("Visual Arts", "ink", "Ink"),
    ("Visual Arts", "charcoal", "Charcoal"),
    ("Visual Arts", "pastel", "Pastel"),
    ("Visual Arts", "printmaking", "Printmaking"),
    ("Visual Arts", "comics", "Comics"),
    ("Visual Arts", "manga", "Manga"),
    ("Visual Arts", "concept-art", "Concept Art"),
    ("Visual Arts", "character-design", "Character Design"),
    ("Visual Arts", "storyboarding", "Storyboarding"),
    ("Visual Arts", "mural", "Mural"),
    ("Visual Arts", "fine-art-photography", "Fine Art Photography"),
    # V2. Music & Audio
    ("Music & Audio", "singer", "Singer"),
    ("Music & Audio", "songwriter", "Songwriter"),
    ("Music & Audio", "lyricist", "Lyricist"),
    ("Music & Audio", "music-producer", "Music Producer"),
    ("Music & Audio", "beatmaker", "Beatmaker"),
    ("Music & Audio", "dj", "DJ"),
    ("Music & Audio", "instrumentalist-guitar", "Guitarist"),
    ("Music & Audio", "instrumentalist-piano", "Pianist"),
    ("Music & Audio", "instrumentalist-strings", "Strings Instrumentalist"),
    ("Music & Audio", "instrumentalist-percussion", "Percussionist"),
    ("Music & Audio", "vocalist-rap", "Rapper"),
    ("Music & Audio", "vocalist-rnb", "R&B Vocalist"),
    ("Music & Audio", "vocalist-indie", "Indie Vocalist"),
    ("Music & Audio", "vocalist-classical", "Classical Vocalist"),
    ("Music & Audio", "audio-engineer", "Audio Engineer"),
    ("Music & Audio", "mixing", "Mixing Engineer"),
    ("Music & Audio", "mastering", "Mastering Engineer"),
    ("Music & Audio", "sound-design", "Sound Designer"),
    ("Music & Audio", "foley", "Foley Artist"),
    ("Music & Audio", "podcast-host", "Podcast Host"),
    # V3. Performing Arts
    ("Performing Arts", "actor-film", "Film Actor"),
    ("Performing Arts", "actor-theatre", "Theatre Actor"),
    ("Performing Arts", "actor-voice", "Voice Actor"),
    ("Performing Arts", "dancer-contemporary", "Contemporary Dancer"),
    ("Performing Arts", "dancer-hiphop", "Hip-Hop Dancer"),
    ("Performing Arts", "dancer-classical", "Classical Dancer"),
    ("Performing Arts", "choreographer", "Choreographer"),
    ("Performing Arts", "stand-up-comedian", "Stand-Up Comedian"),
    ("Performing Arts", "improv-performer", "Improv Performer"),
    ("Performing Arts", "theatre-director", "Theatre Director"),
    ("Performing Arts", "musical-theatre", "Musical Theatre Performer"),
    ("Performing Arts", "drag-performer", "Drag Performer"),
    ("Performing Arts", "performance-artist", "Performance Artist"),
    ("Performing Arts", "circus-arts", "Circus Arts Performer"),
    # V4. Film, Video & Animation
    ("Film, Video & Animation", "director", "Director"),
    ("Film, Video & Animation", "cinematographer", "Cinematographer"),
    ("Film, Video & Animation", "video-editor", "Video Editor"),
    ("Film, Video & Animation", "colorist", "Colorist"),
    ("Film, Video & Animation", "gaffer", "Gaffer"),
    ("Film, Video & Animation", "sound-recordist", "Sound Recordist"),
    ("Film, Video & Animation", "animator-2d", "2D Animator"),
    ("Film, Video & Animation", "animator-3d", "3D Animator"),
    ("Film, Video & Animation", "motion-graphics", "Motion Graphics Designer"),
    ("Film, Video & Animation", "vfx-artist", "VFX Artist"),
    ("Film, Video & Animation", "screenwriter", "Screenwriter"),
    ("Film, Video & Animation", "documentarian", "Documentary Filmmaker"),
    ("Film, Video & Animation", "music-video-director", "Music Video Director"),
    ("Film, Video & Animation", "content-creator-shortform", "Short-Form Creator"),
    ("Film, Video & Animation", "content-creator-longform", "Long-Form Creator"),
    ("Film, Video & Animation", "youtuber", "YouTuber"),
    # V5. Design
    ("Design", "graphic-design", "Graphic Designer"),
    ("Design", "brand-identity", "Brand Identity Designer"),
    ("Design", "type-designer", "Type Designer"),
    ("Design", "ui-designer", "UI Designer"),
    ("Design", "ux-designer", "UX Designer"),
    ("Design", "product-designer", "Product Designer"),
    ("Design", "industrial-designer", "Industrial Designer"),
    ("Design", "fashion-designer", "Fashion Designer"),
    ("Design", "textile-designer", "Textile Designer"),
    ("Design", "jewelry-designer", "Jewelry Designer"),
    ("Design", "interior-designer", "Interior Designer"),
    ("Design", "set-designer", "Set Designer"),
    ("Design", "costume-designer", "Costume Designer"),
    ("Design", "web-designer", "Web Designer"),
    ("Design", "packaging-designer", "Packaging Designer"),
    ("Design", "illustrator-commercial", "Commercial Illustrator"),
    # V6. Writing & Literature
    ("Writing & Literature", "novelist", "Novelist"),
    ("Writing & Literature", "short-fiction-writer", "Short Fiction Writer"),
    ("Writing & Literature", "poet", "Poet"),
    ("Writing & Literature", "essayist", "Essayist"),
    ("Writing & Literature", "journalist", "Journalist"),
    ("Writing & Literature", "copywriter", "Copywriter"),
    ("Writing & Literature", "screenwriter-feature", "Feature Screenwriter"),
    ("Writing & Literature", "screenwriter-tv", "TV Screenwriter"),
    ("Writing & Literature", "playwright", "Playwright"),
    ("Writing & Literature", "ghostwriter", "Ghostwriter"),
    ("Writing & Literature", "editor", "Editor"),
    ("Writing & Literature", "translator", "Translator"),
    ("Writing & Literature", "literary-critic", "Literary Critic"),
    ("Writing & Literature", "technical-writer", "Technical Writer"),
    ("Writing & Literature", "newsletter-author", "Newsletter Author"),
    ("Writing & Literature", "zine-maker", "Zine Maker"),
    # V7. Digital, Code & New Media
    ("Digital, Code & New Media", "creative-technologist", "Creative Technologist"),
    ("Digital, Code & New Media", "generative-artist", "Generative Artist"),
    ("Digital, Code & New Media", "interactive-designer", "Interactive Designer"),
    ("Digital, Code & New Media", "ar-vr-creator", "AR/VR Creator"),
    ("Digital, Code & New Media", "game-designer", "Game Designer"),
    ("Digital, Code & New Media", "game-developer", "Game Developer"),
    ("Digital, Code & New Media", "indie-dev-solo", "Indie Developer (Solo)"),
    ("Digital, Code & New Media", "web3-creator", "Web3 Creator"),
    ("Digital, Code & New Media", "ai-artist", "AI Artist"),
    ("Digital, Code & New Media", "immersive-installation-artist", "Immersive Installation Artist"),
    ("Digital, Code & New Media", "software-artist", "Software Artist"),
    ("Digital, Code & New Media", "data-visualization", "Data Visualization Artist"),
    ("Digital, Code & New Media", "livecoder", "Livecoder"),
    ("Digital, Code & New Media", "modder", "Modder"),
    # V8. Craft, Fashion & Maker
    ("Craft, Fashion & Maker", "ceramicist", "Ceramicist"),
    ("Craft, Fashion & Maker", "sculptor", "Sculptor"),
    ("Craft, Fashion & Maker", "glassblower", "Glassblower"),
    ("Craft, Fashion & Maker", "woodworker", "Woodworker"),
    ("Craft, Fashion & Maker", "leatherworker", "Leatherworker"),
    ("Craft, Fashion & Maker", "metalsmith", "Metalsmith"),
    ("Craft, Fashion & Maker", "jeweler-maker", "Jewelry Maker"),
    ("Craft, Fashion & Maker", "fashion-pattern-maker", "Fashion Pattern Maker"),
    ("Craft, Fashion & Maker", "tailor", "Tailor"),
    ("Craft, Fashion & Maker", "milliner", "Milliner"),
    ("Craft, Fashion & Maker", "knitter-fiber", "Knitter / Fiber Artist"),
    ("Craft, Fashion & Maker", "embroidery", "Embroidery Artist"),
    ("Craft, Fashion & Maker", "screen-printer", "Screen Printer"),
    ("Craft, Fashion & Maker", "bookbinder", "Bookbinder"),
    ("Craft, Fashion & Maker", "candlemaker", "Candlemaker"),
    ("Craft, Fashion & Maker", "perfumer", "Perfumer"),
    ("Craft, Fashion & Maker", "floral-designer", "Floral Designer"),
    # V9. Producing, Curation & Direction
    ("Producing, Curation & Direction", "creative-director", "Creative Director"),
    ("Producing, Curation & Direction", "art-director", "Art Director"),
    ("Producing, Curation & Direction", "music-director", "Music Director"),
    ("Producing, Curation & Direction", "producer-film", "Film Producer"),
    ("Producing, Curation & Direction", "producer-music", "Music Producer (Business)"),
    ("Producing, Curation & Direction", "producer-theatre", "Theatre Producer"),
    ("Producing, Curation & Direction", "producer-events", "Events Producer"),
    ("Producing, Curation & Direction", "curator-gallery", "Gallery Curator"),
    ("Producing, Curation & Direction", "curator-music", "Music Curator"),
    ("Producing, Curation & Direction", "festival-programmer", "Festival Programmer"),
    ("Producing, Curation & Direction", "booker", "Booker"),
    ("Producing, Curation & Direction", "manager-artist", "Artist Manager"),
    ("Producing, Curation & Direction", "label-founder", "Label Founder"),
    ("Producing, Curation & Direction", "magazine-founder", "Magazine Founder"),
    ("Producing, Curation & Direction", "gallery-founder", "Gallery Founder"),
    ("Producing, Curation & Direction", "collective-organizer", "Collective Organizer"),
    ("Producing, Curation & Direction", "creative-strategist", "Creative Strategist"),
]

# ---------------------------------------------------------------------------
# Personality quiz seed (plan §5.1)
# ---------------------------------------------------------------------------

PERSONALITY_QUESTIONS_SEED = [
    {
        "question_key": "work_pace",
        "prompt": "When you're deep in a project, you…",
        "sort_order": 1,
        "options": [
            {"answer_key": "a", "label": "plan every beat ahead", "weights": {"architect": 0.7, "connector": 0.3}},
            {"answer_key": "b", "label": "ride the wave and edit later", "weights": {"mystic": 0.6, "maverick": 0.4}},
            {"answer_key": "c", "label": "ship a draft, then obsess", "weights": {"craftsperson": 0.7, "storyteller": 0.3}},
            {"answer_key": "d", "label": "need a collaborator in the room", "weights": {"connector": 0.8, "producer": 0.2}},
        ],
    },
    {
        "question_key": "feedback_style",
        "prompt": "Best feedback you ever got was…",
        "sort_order": 2,
        "options": [
            {"answer_key": "a", "label": "brutally specific", "weights": {"architect": 0.5, "craftsperson": 0.5}},
            {"answer_key": "b", "label": "emotionally validating", "weights": {"mystic": 0.6, "connector": 0.4}},
            {"answer_key": "c", "label": "one provocative question", "weights": {"maverick": 0.7, "producer": 0.3}},
            {"answer_key": "d", "label": "'I'd buy this'", "weights": {"showrunner": 0.6, "producer": 0.4}},
        ],
    },
    {
        "question_key": "risk_appetite",
        "prompt": "You'd rather…",
        "sort_order": 3,
        "options": [
            {"answer_key": "a", "label": "nail what you know", "weights": {"craftsperson": 0.7, "architect": 0.3}},
            {"answer_key": "b", "label": "invent a new lane", "weights": {"maverick": 0.8, "mystic": 0.2}},
            {"answer_key": "c", "label": "translate between worlds", "weights": {"connector": 0.6, "storyteller": 0.4}},
            {"answer_key": "d", "label": "scale what works", "weights": {"producer": 0.7, "showrunner": 0.3}},
        ],
    },
    {
        "question_key": "collab_role",
        "prompt": "In a duo, you naturally…",
        "sort_order": 4,
        "options": [
            {"answer_key": "a", "label": "set the vision", "weights": {"architect": 0.5, "showrunner": 0.5}},
            {"answer_key": "b", "label": "hold the room together", "weights": {"connector": 0.8, "producer": 0.2}},
            {"answer_key": "c", "label": "push the weird", "weights": {"maverick": 0.6, "mystic": 0.4}},
            {"answer_key": "d", "label": "polish the output", "weights": {"craftsperson": 0.8, "storyteller": 0.2}},
        ],
    },
    {
        "question_key": "success_metric",
        "prompt": "A project is 'done' when…",
        "sort_order": 5,
        "options": [
            {"answer_key": "a", "label": "it's perfect", "weights": {"craftsperson": 0.8, "architect": 0.2}},
            {"answer_key": "b", "label": "it moves someone", "weights": {"storyteller": 0.7, "mystic": 0.3}},
            {"answer_key": "c", "label": "people are using it", "weights": {"producer": 0.6, "showrunner": 0.4}},
            {"answer_key": "d", "label": "it changed your mind", "weights": {"maverick": 0.6, "mystic": 0.4}},
        ],
    },
    {
        "question_key": "energy_source",
        "prompt": "You're recharged by…",
        "sort_order": 6,
        "options": [
            {"answer_key": "a", "label": "solitude + a notebook", "weights": {"mystic": 0.7, "craftsperson": 0.3}},
            {"answer_key": "b", "label": "a packed studio session", "weights": {"connector": 0.6, "showrunner": 0.4}},
            {"answer_key": "c", "label": "blueprint + spreadsheets", "weights": {"architect": 0.7, "producer": 0.3}},
            {"answer_key": "d", "label": "an argument worth having", "weights": {"maverick": 0.6, "storyteller": 0.4}},
        ],
    },
]


def upgrade() -> None:
    # Create vocation_taxonomy
    op.create_table(
        "vocation_taxonomy",
        sa.Column("category", sa.String(64), primary_key=True),
        sa.Column("subtag", sa.String(128), primary_key=True),
        sa.Column("display", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )

    # Create personality_questions
    op.create_table(
        "personality_questions",
        sa.Column("question_key", sa.String(64), primary_key=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )

    # Seed taxonomy
    for sort_order, (category, subtag, display) in enumerate(TAXONOMY_SEED):
        op.execute(
            sa.text(
                "INSERT INTO vocation_taxonomy (category, subtag, display, sort_order) "
                "VALUES (:category, :subtag, :display, :sort_order) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(category=category, subtag=subtag, display=display, sort_order=sort_order)
        )

    # Seed personality questions
    import json as _json
    for q in PERSONALITY_QUESTIONS_SEED:
        op.execute(
            sa.text(
                "INSERT INTO personality_questions (question_key, prompt, options, sort_order) "
                "VALUES (:key, :prompt, CAST(:options AS JSONB), :sort_order) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                key=q["question_key"],
                prompt=q["prompt"],
                options=_json.dumps(q["options"]),
                sort_order=q["sort_order"],
            )
        )


def downgrade() -> None:
    op.drop_table("personality_questions")
    op.drop_table("vocation_taxonomy")
