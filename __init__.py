"""Image Gen Provider — infocepo TXT2IMAGE (OpenAI-compatible /v1/images/generations)."""
from typing import Any, Dict, List, Optional
import os
import logging

logger = logging.getLogger(__name__)

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    save_b64_image,
    success_response,
)


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
                "strengths": "Text-to-image generation via infocepo",
            },
        ]

    def default_model(self) -> Optional[str]:
        return "default"

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Infocepo TXT2IMAGE",
            "tag": "API TXT2IMAGE — infocepo.com",
            "env_vars": [
                {
                    "key": "TXT2IMAGE_API_KEY",
                    "prompt": "TXT2IMAGE API key",
                    "url": "https://infocepo.com/wiki/index.php/Main_Page#API_Text_to_Image",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Génère une image via l'API TXT2IMAGE d'infocepo."""
        import requests

        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_input",
                provider=self.name,
            )

        api_key = os.environ.get("TXT2IMAGE_API_KEY")
        if not api_key:
            return error_response(
                error="TXT2IMAGE_API_KEY not set in environment",
                error_type="invalid_input",
                provider=self.name,
            )

        base_url = "https://api-txt2image.ailab.infocepo.com/v1"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # Mapper aspect_ratio → size (API attend un format "WxH")
        # Sizes validées par l'API : ['1024x1024', '512x512', '768x768']
        aspect_to_size = {
            "landscape": "768x768",
            "portrait": "768x768",
            "square": "1024x1024",
        }
        target_size = aspect_to_size.get(aspect_ratio, "1024x1024")

        payload: Dict[str, Any] = {
            "prompt": prompt,
            "n": 1,
            "size": target_size,
            "steps": kwargs.get("steps", 20),
            "guidance_scale": kwargs.get("guidance_scale", 7.0),
            "response_format": "b64_json",
        }
        if kwargs.get("seed") is not None:
            payload["seed"] = kwargs["seed"]
        if kwargs.get("negative_prompt"):
            payload["negative_prompt"] = kwargs["negative_prompt"]

        try:
            logger.debug("TXT2IMAGE request: %s", payload)
            resp = requests.post(
                f"{base_url}/images/generations",
                json=payload,
                headers=headers,
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
                        aspect_ratio=aspect_ratio,
                        provider=self.name,
                        modality="text",
                    )

            return error_response(
                error="Unexpected API response format (no b64_json in data)",
                error_type="provider_error",
                provider=self.name,
                prompt=prompt,
            )

        except requests.exceptions.Timeout:
            return error_response(
                error="Request timed out after 120s (model may be warming up)",
                error_type="timeout",
                provider=self.name,
                prompt=prompt,
            )
        except requests.exceptions.HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.response.text[:500]
            except Exception:
                pass
            return error_response(
                error=f"HTTP {exc.response.status_code}: {error_body}" or str(exc),
                error_type="provider_error",
                provider=self.name,
                prompt=prompt,
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
