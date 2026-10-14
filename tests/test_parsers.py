import httpx
import pytest

from prompt_registry.models import Source
from prompt_registry.parsers import (
    parse_awesome_gpt4o,
    parse_awesome_gpt_image,
    parse_banana_json,
    parse_freestylefly_json,
    parse_picotrex,
    parse_source,
    parse_seedance,
    parse_youmind,
    parse_youmind_skill_midjourney,
    parse_zerolu_nanobanana,
    youmind_skill_files,
)
from prompt_registry.sync import fetch_one


def source(adapter: str, *, model: str = "") -> Source:
    return Source(
        id="test-source",
        name="Test",
        adapter=adapter,
        url="https://raw.githubusercontent.com/example/repo/main/README.md",
        homepage="https://github.com/example/repo",
        minimum_items=1,
        model=model,
    )


def test_banana_json_maps_reference_data() -> None:
    payload = b'''[
      {
        "title": "Poster",
        "prompt": "Create a poster",
        "preview": "https://example.com/cover.png",
        "reference_image_urls": ["https://example.com/ref.png"],
        "author": "Author",
        "category": "Work",
        "sub_category": "Poster",
        "created": "2026-01-01",
        "mode": "generate"
      }
    ]'''
    item = parse_banana_json(source("banana-json"), payload)[0]
    assert item["title"] == "Poster"
    assert item["referenceImageUrls"] == ["https://example.com/ref.png"]
    assert item["tags"] == ["Work", "Poster", "Author"]


def test_freestylefly_json_maps_case_data() -> None:
    payload = b'''{
      "cases": [
        {
          "id": 7,
          "title": "Architecture",
          "image": "/images/case7.jpg",
          "sourceLabel": "Alice",
          "sourceUrl": "",
          "prompt": "Create an architectural rendering.",
          "category": "Architecture & Spaces",
          "styles": ["3D"],
          "scenes": ["Commerce"],
          "featured": true,
          "githubUrl": "https://github.com/example/repo/blob/main/gallery.md#case-7"
        }
      ]
    }'''
    item = parse_freestylefly_json(
        Source(
            id="test-source",
            name="Test",
            adapter="freestylefly-json",
            url="https://raw.githubusercontent.com/example/repo/main/data/cases.json",
            homepage="https://github.com/example/repo",
            minimum_items=1,
            model="gpt-image-2",
        ),
        payload,
    )[0]
    image_url = "https://raw.githubusercontent.com/example/repo/main/data/images/case7.jpg"
    assert item["coverUrl"] == image_url
    assert item["referenceImageUrls"] == [image_url]
    assert item["sourceUrl"] == "https://github.com/example/repo/blob/main/gallery.md#case-7"
    assert item["author"] == "Alice"
    assert item["tags"] == [
        "gpt-image-2",
        "Architecture & Spaces",
        "3D",
        "Commerce",
        "featured",
    ]
    assert item["imageModel"] == "gpt-image-2"


def test_parse_source_rejects_results_below_minimum_items() -> None:
    configured_source = Source(
        id="test-source",
        name="Test",
        adapter="freestylefly-json",
        url="https://raw.githubusercontent.com/example/repo/main/data/cases.json",
        homepage="https://github.com/example/repo",
        minimum_items=2,
        model="gpt-image-2",
    )
    payload = b'''{
      "cases": [
        {"id": 1, "title": "Only case", "prompt": "Create an image."}
      ]
    }'''

    with pytest.raises(ValueError, match="produced 1 items; expected at least 2"):
        parse_source(configured_source, payload)


def test_awesome_markdown_uses_fenced_prompt_and_images() -> None:
    payload = """
## Photography
### Night scene
<img src="images/night.png">

**Prompt:**
```text
Create a realistic night scene.
```
**Source:** [Alice](https://example.com/post)
""".replace("Prompt", "提示词").replace("Source", "来源").encode()
    item = parse_awesome_gpt_image(source("awesome-gpt-image-markdown"), payload)[0]
    assert item["prompt"] == "Create a realistic night scene."
    assert item["coverUrl"].endswith("/main/images/night.png")
    assert item["author"] == "Alice"


def test_awesome_markdown_does_not_use_image_alt_text_as_description() -> None:
    payload = """
### Product image

![A generated product](images/product.png)

The actual description.

- **模型:** gpt4o
- **提示词文本:** `Create a product image.`
""".encode()
    item = parse_awesome_gpt4o(source("awesome-gpt4o-markdown"), payload)[0]
    assert item["description"] == "The actual description."


def test_awesome_markdown_keeps_prompts_that_share_a_source_url() -> None:
    payload = """
### First
**提示词:**
```
Create the first image.
```
**来源:** [Alice](https://example.com/post)

### Second
**提示词:**
```
Create the second image.
```
**来源:** [Alice](https://example.com/post)
""".encode()
    items = parse_awesome_gpt_image(source("awesome-gpt-image-markdown"), payload)
    assert len(items) == 2
    assert items[0]["id"] != items[1]["id"]


def test_gpt4o_markdown_reads_prompt_spanning_paragraphs() -> None:
    payload = """
### Product card

- **提示词文本:** `Create a product card with

several clearly separated sections.`
""".encode()
    item = parse_awesome_gpt4o(source("awesome-gpt4o-markdown"), payload)[0]
    assert item["prompt"] == "Create a product card with\n\nseveral clearly separated sections."


def test_gpt4o_markdown_uses_inline_code_prompt() -> None:
    payload = """
### Product card

A short description.

- **Model:** gpt4o
- **Prompt text:** `Create a clean product card.`
- **Example:** <img src="https://example.com/card.png">
- **Author:** [Bob](https://example.com/bob)
""".replace("Model", "模型").replace("Prompt text", "提示词文本").replace("Example", "示例图片").replace("Author", "作者").encode()
    item = parse_awesome_gpt4o(source("awesome-gpt4o-markdown"), payload)[0]
    assert item["prompt"] == "Create a clean product card."
    assert item["description"] == "A short description."
    assert item["imageModel"] == "gpt4o"


def test_youmind_markdown_reads_description_date_and_prompt() -> None:
    payload = """
### No. 7: Education - Diagram

#### Description
A useful diagram.

#### Prompt
```
Create a detailed diagram.
```

#### Images
<img src="https://example.com/diagram.png">

#### Details
- **Author:** [Carol](https://example.com/carol)
- **Source:** [Post](https://example.com/post)
- **Published:** 2026年4月19日
""".replace("Description", "描述").replace("Prompt", "提示词").replace("Images", "生成图片").replace("Details", "详情").replace("Author", "作者").replace("Source", "来源").replace("Published", "发布时间").encode()
    item = parse_youmind(source("youmind-markdown", model="gpt-image-2"), payload)[0]
    assert item["title"] == "Education - Diagram"
    assert item["description"] == "A useful diagram."
    assert item["createdAt"] == "2026-04-19"
    assert item["sourceUrl"] == "https://example.com/post"
    assert item["tags"] == ["gpt-image-2", "Education", "Carol"]


def test_youmind_keeps_different_prompts_with_the_same_number() -> None:
    payload = """
### No. 1: First
#### 提示词
```
Create the first image.
```

### No. 1: Second
#### 提示词
```
Create the second image.
```
""".encode()
    items = parse_youmind(source("youmind-markdown", model="gpt-image-2"), payload)
    assert len(items) == 2
    assert items[0]["id"] != items[1]["id"]


def test_seedance_markdown_reads_numbered_and_catalog_entries() -> None:
    payload = """
## ⭐ 精选提示词
### No. 1: Featured film
#### 📝 提示词
```text
Create a cinematic video.
```
<img src="media/featured.jpg">
**作者:** [Alice](https://x.com/alice) | **来源:** [Post](https://x.com/post) | **发布时间:** March 15, 2026

## 🎬 所有提示词
### Unnumbered catalog entry
> A short description.
#### 📝 提示词
```text
Create a catalog video.
```
<img src="media/catalog.jpg">
**作者:** [Bob](https://x.com/bob) | **来源:** [Link](https://x.com/link) | **发布时间:** Aug 30, 2026
""".encode()
    item_source = Source(
        id="seedance",
        name="Seedance",
        adapter="seedance-markdown",
        url="https://raw.githubusercontent.com/YouMind-OpenLab/awesome-seedance-2-prompts/main/README_zh.md",
        homepage="https://github.com/YouMind-OpenLab/awesome-seedance-2-prompts",
        minimum_items=1,
        model="seedance-2",
    )
    items = parse_seedance(item_source, payload)
    assert len(items) == 2
    assert items[1]["title"] == "Unnumbered catalog entry"
    assert items[1]["coverUrl"].endswith("/main/media/catalog.jpg")
    assert items[1]["sourceUrl"] == "https://x.com/link"
    assert items[1]["createdAt"] == "2026-08-30"


def test_zerolu_markdown_reads_numbered_english_entries() -> None:
    payload = """
### Sponsor1
Not a prompt.

## 1. Photorealism & Aesthetics
### 1.1. Hyper-Realistic Crowd
*Handling complex compositions.*
<img width="400" alt="Crowd" src="https://github.com/user-attachments/assets/crowd.png" />

**Prompt:**
```text
Create a hyper-realistic crowd.
```
*Source: [@Seb](https://x.com/Seb/status/1)*
""".encode()
    items = parse_zerolu_nanobanana(source("zerolu-nanobanana-markdown", model="nano-banana-pro"), payload)
    assert len(items) == 1
    assert items[0]["title"] == "Hyper-Realistic Crowd"
    assert items[0]["prompt"] == "Create a hyper-realistic crowd."
    assert items[0]["description"] == "Handling complex compositions."
    assert items[0]["coverUrl"] == "https://github.com/user-attachments/assets/crowd.png"
    assert items[0]["author"] == "@Seb"
    assert items[0]["sourceUrl"] == "https://x.com/Seb/status/1"
    assert items[0]["imageModel"] == "nano-banana-pro"
    assert "Photorealism & Aesthetics" in items[0]["tags"]


def test_picotrex_markdown_reads_title_author_and_relative_image() -> None:
    payload = """
## 案例
### 例 1: [浮世绘闪卡](https://x.com/a/status/1)（by [@MANISH](https://x.com/MANISH)）

| 输出 |
| :--: |
| <img src="images/pro_case1/output.jpg" width="300" alt="输出结果"> |

**提示词:**

```
一张日式浮世绘风格的卡牌。
```

> [!NOTE]
> **需要在提示词中 {} 输入需要的信息**

### 不是案例的小节
正文。
""".encode()
    items = parse_picotrex(source("picotrex-markdown", model="nano-banana"), payload)
    assert len(items) == 1
    assert items[0]["title"] == "浮世绘闪卡"
    assert items[0]["author"] == "@MANISH"
    assert items[0]["prompt"] == "一张日式浮世绘风格的卡牌。"
    assert items[0]["coverUrl"] == "https://raw.githubusercontent.com/example/repo/main/images/pro_case1/output.jpg"
    assert items[0]["imageModel"] == "nano-banana"


def test_youmind_skill_files_resolve_relative_to_manifest() -> None:
    manifest_source = Source(
        id="test-source",
        name="Test",
        adapter="youmind-skill-midjourney",
        url="https://raw.githubusercontent.com/example/repo/main/references/manifest.json",
        homepage="https://github.com/example/repo",
        minimum_items=1,
        model="midjourney",
    )
    payload = b'{"categories": [{"title": "Poster / Flyer", "file": "poster-flyer.json"}]}'
    assert youmind_skill_files(manifest_source, payload) == [
        ("Poster / Flyer", "https://raw.githubusercontent.com/example/repo/main/references/poster-flyer.json")
    ]
    with pytest.raises(ValueError, match="categories array"):
        youmind_skill_files(manifest_source, b'{"categories": []}')


def test_youmind_skill_midjourney_keeps_only_midjourney_parameters() -> None:
    payload = b'''{"categories": [
      {"title": "Poster / Flyer", "items": [
        {"id": 1, "title": "Zine", "content": "Ink zine poster --ar 9:16 --stylize 750",
         "description": "Bold zine.", "sourceMedia": ["https://example.com/zine.png"], "needReferenceImages": false},
        {"id": 2, "title": "Ratio only", "content": "A portrait --ar 3:4", "sourceMedia": []},
        {"id": 3, "title": "Prose", "content": "Made in Midjourney, then upscaled", "sourceMedia": []}
      ]},
      {"title": "Others", "items": [
        {"id": 1, "title": "Zine", "content": "Ink zine poster --ar 9:16 --stylize 750",
         "sourceMedia": ["https://example.com/zine.png"]},
        {"id": 4, "title": "Anime", "content": "Anime girl --niji 6", "sourceMedia": [], "needReferenceImages": true}
      ]}
    ]}'''
    items = parse_youmind_skill_midjourney(source("youmind-skill-midjourney", model="midjourney"), payload)
    assert [item["title"] for item in items] == ["Zine", "Anime"]
    assert items[0]["coverUrl"] == "https://example.com/zine.png"
    assert items[0]["description"] == "Bold zine."
    assert items[0]["imageModel"] == "midjourney"
    assert items[0]["tags"] == ["midjourney", "Poster / Flyer"]
    assert items[1]["tags"] == ["midjourney", "Others", "需要参考图"]


def test_youmind_skill_midjourney_rejects_non_array_category() -> None:
    payload = b'{"categories": [{"title": "Broken", "items": {"id": 1}}]}'
    with pytest.raises(ValueError, match="JSON arrays of objects"):
        parse_youmind_skill_midjourney(source("youmind-skill-midjourney", model="midjourney"), payload)


def test_fetch_one_joins_bundle_files_listed_in_manifest() -> None:
    base = "https://raw.githubusercontent.com/example/repo/main/references/"
    responses = {
        base + "manifest.json": b'{"categories": [{"title": "A", "file": "a.json"}, {"title": "B", "file": "b.json"}]}',
        base + "a.json": '﻿[{"id": 1, "title": "One", "content": "x --v 6"}]'.encode(),
        base + "b.json": b'[{"id": 2, "title": "Two", "content": "y --sref 123"}]',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = responses.get(str(request.url))
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)

    bundle_source = Source(
        id="test-source",
        name="Test",
        adapter="youmind-skill-midjourney",
        url=base + "manifest.json",
        homepage="https://github.com/example/repo",
        minimum_items=2,
        model="midjourney",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items = fetch_one(client, bundle_source)
    assert [item["title"] for item in items] == ["One", "Two"]

    del responses[base + "b.json"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_one(client, bundle_source)
