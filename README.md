# Hermes Image Generation — Infocepo TXT2IMAGE

Plugin Hermes Agent pour la génération d'images via l'API TXT2IMAGE d'infocepo.com.

## Source de l'API

- URL de base : `https://api-txt2image.ailab.infocepo.com/v1`
- Documentation : [Main Page #API_Text_to_Image](https://infocepo.com/wiki/index.php/Main_Page#API_Text_to_Image)
- OpenAPI / Swagger : [Swagger UI](https://api-txt2image.ailab.infocepo.com/docs)

## Installation

### 1. Copier le plugin dans ~/.hermes/plugins/image_gen/

```bash
mkdir -p ~/.hermes/plugins/image_gen/infocepo-txt2image
cp -r /home/ai-agent/work/hermes-img-gen-infocepo/* ~/.hermes/plugins/image_gen/infocepo-txt2image/
```

### 2. Ajouter la clé API

```bash
echo 'TXT2IMAGE_API_KEY=sk-votre-cle' >> ~/.hermes/.env
```

La clé se trouve sur le wiki : [Main Page #API_Text_to_Image](https://infocepo.com/wiki/index.php/Main_Page#API_Text_to_Image)

### 3. Activer le plugin

```bash
hermes plugins enable infocepo-txt2image
```

### 4. Sélectionner comme provider

Via l'interactif :

```bash
hermes tools
# → Image Generation → sélectionner "infocepo-txt2image"
```

Ou en éditant `~/.hermes/config.yaml` :

```yaml
image_gen:
  provider: infocepo-txt2image
```

### 5. Redémarrer Hermes

```bash
hermes gateway restart
# ou faire /reset en session
```

## Test

```bash
hermes chat -q "Génère une image d'un corgi dans l'espace"
```

## Spécification de l'API

### Endpoint

```
POST /v1/images/generations
```

### Body

| Champ | Type | Requis | Défaut |
|---|---|---|---|
| `prompt` | string | ✅ | — |
| `n` | integer | ❌ | 1 (max 8) |
| `size` | string | ❌ | `1024x1024` |
| `steps` | integer | ❌ | 20 (max 150) |
| `guidance_scale` | number | ❌ | 7.0 |
| `seed` | integer | ❌ | null |
| `negative_prompt` | string | ❌ | null |
| `response_format` | string | ❌ | `b64_json` |

### Réponse

```json
{
  "data": [
    {
      "b64_json": "base64_encoded_image_data..."
    }
  ]
}
```

### Authentification

```
Authorization: Bearer <api_key>
Content-Type: application/json
```

## Structure du plugin

```
plugins/image_gen/infocepo-txt2image/
├── __init__.py          # Provider ImageGen + register()
└── plugin.yaml          # Manifest
```

## Exemple de curl

```bash
export TXT2IMAGE_API_KEY=sk-...

curl -s https://api-txt2image.ailab.infocepo.com/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TXT2IMAGE_API_KEY" \
  -d '{
    "prompt": "a photo of a happy corgi puppy sitting and facing forward, studio light, longshot",
    "n": 1,
    "size": "1024x1024"
  }' | jq .
```

## Licence

MIT — basée sur les conventions Hermes Agent.
