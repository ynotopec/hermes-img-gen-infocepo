"""Image Gen Provider — infocepo TXT2IMAGE (OpenAI-compatible, generation + editing).

The infocepo TXT2IMAGE API mirrors the OpenAI Images API:

* ``POST /v1/images/generations`` — JSON body (text-to-image)
* ``POST /v1/images/edits``       — ``multipart/form-data`` (image-to-image / editing)

One Hermes tool (``image_generate``) covers both: with source images the tool routes
here with ``image_url`` / ``reference_image_urls`` set, which this provider sends to the
edit endpoint; without them it stays text-to-image.
"""
from typing import Any, Dict, List, Optional, Tuple
import os
import base64
import mimetypes
import logging

logger = logging.getLogger(__name__)

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

BASE_URL = "https://api-txt2image.ailab.infocepo.com/v1"
# The edit endpoint accepts `image` plus `image[]`; cap the total sources.
MAX_REFERENCE_IMAGES = 4

ASPECT_TO_SIZE = {
    "landscape": "1280x720",
    "portrait": "720x1280",
    "square": "1024x1024",
}


def _collect_sources(
    image_url: Optional[str], reference_image_urls: Optional[List[str]]
) -> List[str]:
    """Primary ``image_url`` first, then references, clamped to ``MAX_REFERENCE_IMAGES``."""
    sources: List[str] = []
    if isinstance(image_url, str) and image_url.strip():
        sources.append(image_url.strip())
    refs = reference_image_urls
    if isinstance(refs, str):
        refs = [refs]
    if isinstance(refs, (list, tuple)):
        sources.extend(
            item.strip() for item in refs if isinstance(item, str) and item.strip()
        )
    return sources[:MAX_REFERENCE_IMAGES]


def _load_image_bytes(ref: str) -> Tuple[bytes, str, str]:
    """Load ``(data, filename, content_type)`` from a URL, data URI or local path."""
    ref = ref.strip()
    lower = ref.lower()
    if lower.startswith(("http://", "https://")):
        import requests

        resp = requests.get(ref, timeout=60)
        resp.raise_for_status()
        name = ref.split("?", 1)[0].rsplit("/", 1)[-1] or "image.png"
        ctype = resp.headers.get("Content-Type") or mimetypes.guess_type(name)[0] or "image/png"
        return resp.content, name, ctype
    if lower.startswith("data:"):
        header, _, b64 = ref.partition(",")
        ext = (header.split("image/", 1)[1].split(";", 1)[0] if "image/" in header else "") or "png"
        return base64.b64decode(b64), f"image.{ext}", f"image/{ext}"
    from agent.file_safety import raise_if_read_blocked  # credential-read guard

    raise_if_read_blocked(ref)
    with open(ref, "rb") as fh:
        data = fh.read()
    name = os.path.basename(ref) or "image.png"
    ctype = mimetypes.guess_type(name)[0] or "image/png"
    return data, name, ctype


class InfocepoTxt2ImageProvider(ImageGenProvider):
    """Backend image-gen pour l'API TXT2IMAGE d'infocepo.com."""

    @property
    def name(self) -> str:
        return "infocepo-txt2image"

    @property
    def display_name(self) -> str:
        return "Infocepo TXT2IMAGE"

    def is_available(self) -> bool:
        return bool(os.environ.get("TXT2IMAGE_API_KEY"))

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "default",
                "display": "Infocepo Default",
                "speed": "~5-15s",
                "strengths": "Text-to-image generation and image editing via infocepo",
            },
        ]

    def default_model(self) -> Optional[str]:
        return "default"

    def capabilities(self) -> Dict[str, Any]:
        # OpenAI-compatible backend: both text-to-image and image-to-image (editing).
        return {"modalities": ["text", "image"], "max_reference_images": MAX_REFERENCE_IMAGES}

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Infocepo TXT2IMAGE",
            "tag": "API TXT2IMAGE — infocepo.com (génération + édition)",
            "env_vars": [
                {
                    "key": "TXT2IMAGE_API_KEY",
                    "prompt": "TXT2IMAGE API key",
                    "url": "https://infocepo.com/wiki/index.php/Main_Page#API_Text_to_Image",
                },
            ],
        }

    def _auth_error(self) -> Dict[str, Any]:
        return error_response(
            error="TXT2IMAGE_API_KEY not set in environment",
            error_type="invalid_input",
            provider=self.name,
        )

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Génère (texte→image) ou édite (image→image) via l'API TXT2IMAGE d'infocepo."""
        import requests

        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_input",
                provider=self.name,
                aspect_ratio=aspect,
            )

        api_key = os.environ.get("TXT2IMAGE_API_KEY")
        if not api_key:
            return self._auth_error()

        auth = {"Authorization": f"Bearer {api_key}"}
        target_size = ASPECT_TO_SIZE.get(aspect, "1024x1024")
        sources = _collect_sources(image_url, reference_image_urls)
        is_edit = bool(sources)

        steps = kwargs.get("steps", 20)
        guidance_scale = kwargs.get("guidance_scale", 7.0)
        seed = kwargs.get("seed")
        negative_prompt = kwargs.get("negative_prompt")

        try:
            if is_edit:
                # OpenAI-compatible edit: multipart/form-data with `image` (+ `image[]`).
                files: List[Tuple[str, Tuple[str, bytes, str]]] = []
                for i, ref in enumerate(sources):
                    data, filename, ctype = _load_image_bytes(ref)
                    field = "image" if i == 0 else "image[]"
                    files.append((field, (filename, data, ctype)))
                form: Dict[str, Any] = {
                    "prompt": prompt,
                    "n": 1,
                    "size": target_size,
                    "response_format": "b64_json",
                    "steps": steps,
                    "guidance_scale": guidance_scale,
                }
                if kwargs.get("strength") is not None:
                    form["strength"] = kwargs["strength"]
                if seed is not None:
                    form["seed"] = seed
                if negative_prompt:
                    form["negative_prompt"] = negative_prompt

                logger.debug("TXT2IMAGE edit request: sources=%d size=%s", len(files), target_size)
                resp = requests.post(
                    f"{BASE_URL}/images/edits",
                    data=form,
                    files=files,
                    headers=auth,
                    timeout=180,
                )
            else:
                # OpenAI-compatible generation: JSON body.
                payload: Dict[str, Any] = {
                    "prompt": prompt,
                    "n": 1,
                    "size": target_size,
                    "steps": steps,
                    "guidance_scale": guidance_scale,
                    "response_format": "b64_json",
                }
                if seed is not None:
                    payload["seed"] = seed
                if negative_prompt:
                    payload["negative_prompt"] = negative_prompt

                logger.debug("TXT2IMAGE generation request: %s", payload)
                resp = requests.post(
                    f"{BASE_URL}/images/generations",
                    json=payload,
                    headers={**auth, "Content-Type": "application/json"},
                    timeout=120,
                )

            resp.raise_for_status()
            data = resp.json()

            # Réponse OpenAI-compatible : data[0].b64_json
            if "data" in data and len(data["data"]) > 0:
                b64 = data["data"][0].get("b64_json")
                if b64:
                    path = save_b64_image(
                        b64, prefix="infocepo_txt2image", extension="png"
                    )
                    return success_response(
                        image=str(path),
                        model="default",
                        prompt=prompt,
                        aspect_ratio=aspect,
                        provider=self.name,
                        modality="image" if is_edit else "text",
                    )

            return error_response(
                error="Unexpected API response format (no b64_json in data)",
                error_type="provider_error",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        except requests.exceptions.Timeout:
            return error_response(
                error="Request timed out (model may be warming up)",
                error_type="timeout",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.exceptions.HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.response.text[:500]
            except Exception:
                pass
            verb = "editing" if is_edit else "generation"
            return error_response(
                error=f"HTTP {exc.response.status_code} ({verb}): {error_body}" or str(exc),
                error_type="provider_error",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except Exception as exc:
            logger.exception("TXT2IMAGE generation failed")
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=self.name,
            )


def register(ctx) -> None:
    """Plugin entry point."""
    ctx.register_image_gen_provider(InfocepoTxt2ImageProvider())
