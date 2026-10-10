# jev-codebook — contrôle d’adoption · adoption check · comprobación de adopción

## Français

Point de départ local, après la préparation indiquée dans le README :

```sh
python3 -m examples.review_export
```

Dans cinq messages de support fictifs, un score incertain doit produire une ligne de revue, pas une étiquette définitive. Ouvrez le CSV et comparez le meilleur candidat avec le texte d’origine.

## English

Local starting point, after the setup described in the README:

```sh
python3 -m examples.review_export
```

For five fictional support messages, an uncertain score should produce a review row, not a final label. Open the CSV and compare the leading candidate with the original text.

## Español

Punto de partida local, después de la preparación descrita en el README:

```sh
python3 -m examples.review_export
```

Para cinco mensajes ficticios de soporte, una puntuación incierta debe crear una fila de revisión y no una etiqueta final. Abra el CSV y compare el candidato principal con el texto original.
## Variante synthétique · Synthetic variation · Variante sintética

```text
top_code_probability=0.52; second_code_probability=0.48
```

FR : adaptez une copie de la fixture locale à cette situation, puis vérifiez le comportement décrit ci-dessus. Les valeurs sont illustratives, pas des résultats Jev mesurés.

EN: adapt a copy of the local fixture to this situation, then check the behavior described above. Values are illustrative, not measured Jev output.

ES: adapte una copia de la fixture local a esta situación y compruebe el comportamiento descrito arriba. Los valores son ilustrativos, no resultados Jev medidos.

## Second cas · Second case · Segundo caso

```text
top_code=none_of_these; next_probability=0.28
```

**FR :** Une réponse hors du codebook doit pouvoir s’abstenir explicitement. Ne forcez pas l’étiquette la plus proche pour remplir une fréquence.

**EN:** An answer outside the codebook should be able to abstain explicitly. Do not force the nearest label to fill a frequency table.

**ES:** Una respuesta fuera del libro de códigos debe poder abstenerse explícitamente. No fuerce la etiqueta más cercana para completar una tabla de frecuencias.
