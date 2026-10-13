# Human review — FR / EN / ES

## Français

Après codage, exporter uniquement les lignes `review`. Sans `--include-text`, le texte reste dans le CSV source. Avec cette option explicite, il est copié tel quel, sans traduction. Modifier uniquement `codes` dans les décisions choisies : une liste de codes connus, ou `[]` pour une abstention humaine explicite. `null` signifie non relu et est refusé à l’application ; supprimer les décisions encore non relues de la file que vous appliquez.

```sh
pip install -e .
jev-codebook-review export coded.csv --codebook codebook.json --out queue.json --include-text --lang fr
# Remplir codes dans queue.json pour les seules décisions relues.
jev-codebook-review apply coded.csv --codebook codebook.json --decisions queue.json --out reviewed.csv --audit review-audit.json --lang fr
```

L’application refuse identifiants inconnus/dupliqués, code inconnu, plusieurs codes en mode single, ligne déjà acceptée, ou empreinte différente du texte, des probabilités, de l’identifiant de requête, des annotations ou du codebook. Toutes les décisions sont validées avant mutation. L’API retourne une copie ; les fichiers source et les probabilités modèle restent inchangés. Le CSV de sortie conserve texte, colonnes utilisateur et représentation des probabilités ; seules annotations et marqueurs de revue changent. Les fréquences de ce CSV combinent désormais annotations modèle et humaines : elles ne mesurent pas la précision du modèle seul.

Les nouvelles sorties sont privées (permissions 600) et ne peuvent écraser des fichiers. Le journal sépare les changements humains des résultats Jev, sans recopier le texte. Il enregistre une annotation explicitement déclarée par l’appelant ; il n’authentifie pas une personne ni la qualité de son jugement. Aucun appel API. Codes de sortie : 0 fichiers produits, 1 entrée, revue ou sortie invalide. Python 3.11+, bibliothèque standard. Les exemples sont synthétiques.

## English

After coding, export only `review` rows. Without `--include-text`, text remains in the source CSV. With this explicit option it is copied unchanged, without translation. Edit only `codes` in selected decisions: known code IDs, or `[]` for explicit human abstention. `null` means unreviewed and is rejected on apply; remove decisions not yet reviewed from the queue you apply.

```sh
pip install -e .
jev-codebook-review export coded.csv --codebook codebook.json --out queue.json --include-text --lang en
# Fill codes in queue.json only for reviewed decisions.
jev-codebook-review apply coded.csv --codebook codebook.json --decisions queue.json --out reviewed.csv --audit review-audit.json --lang en
```

Apply rejects unknown/duplicate IDs, unknown codes, multiple codes in single mode, already accepted rows, or changed fingerprints of text, probabilities, request ID, assignments or codebook. All decisions are validated before mutation. The API returns a copy; source files and model probabilities remain unchanged. Output CSV retains text, user columns and probability representation; only assignments and review flags change. Its frequencies now combine model and human assignments, so they do not measure model accuracy alone.

New outputs are private (mode 600) and cannot overwrite files. The audit separates human changes from Jev results without copying text. It records a caller-declared annotation; it does not authenticate a person or their judgment's quality. No API request. Exit codes: 0 files produced, 1 invalid input/review/output. Python 3.11+, standard library. Examples are synthetic.

## Español

Tras codificar, exportar solo filas `review`. Sin `--include-text`, el texto permanece en el CSV original. Con esta opción explícita se copia sin cambios ni traducción. Editar solo `codes` en decisiones elegidas: identificadores de códigos conocidos, o `[]` para abstención humana explícita. `null` significa sin revisar y se rechaza al aplicar; eliminar de la cola aplicada decisiones todavía no revisadas.

```sh
pip install -e .
jev-codebook-review export coded.csv --codebook codebook.json --out queue.json --include-text --lang es
# Rellenar codes en queue.json solo para decisiones revisadas.
jev-codebook-review apply coded.csv --codebook codebook.json --decisions queue.json --out reviewed.csv --audit review-audit.json --lang es
```

Aplicar rechaza identificadores desconocidos/duplicados, códigos desconocidos, varios códigos en modo single, filas ya aceptadas o cambios en huellas de texto, probabilidades, solicitud, anotaciones o codebook. Valida todas las decisiones antes de mutar. La API devuelve una copia; fuentes y probabilidades del modelo se conservan. El CSV conserva texto, columnas del usuario y representación de probabilidades; solo cambian anotaciones y marcas de revisión. Sus frecuencias mezclan anotaciones humanas y del modelo, por lo que no miden precisión del modelo solo.

Las salidas nuevas son privadas (modo 600) y no sobrescriben archivos. El registro separa cambios humanos de resultados Jev sin copiar texto. Registra anotaciones declaradas por quien llama; no autentica a una persona ni la calidad de su juicio. Sin solicitudes API. Salidas: 0 archivos producidos, 1 entrada/revisión/salida no válida. Python 3.11+, biblioteca estándar. Ejemplos sintéticos.
