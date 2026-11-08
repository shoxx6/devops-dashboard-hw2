# SMS Spam Checker

A small web app that classifies an English SMS message as likely normal or spam. It uses a Multinomial Naive Bayes model trained from the UCI SMS Spam Collection and returns an estimated spam score.

## Run locally

Use Python 3.10 or newer. The app and training code use only the Python standard library.

```powershell
python train_model.py
python app.py
```

Open `http://localhost:10000`. The model and evaluation summary are written to `models/` by the training command. The app exposes `/health` and `POST /api/predict`.

## Docker

```sh
docker build -t sms-spam-checker .
docker run --rm -p 10000:10000 sms-spam-checker
```

Docker trains the model in a build stage and copies only the generated model into the runtime image; the raw message corpus is not included in the final image.

## GitHub Actions and Docker Hub

The workflow builds the image on pull requests and publishes it to Docker Hub on pushes to `main`, using `latest` and commit SHA tags. Add these repository secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

The image name is `shoxx6/devops-dashboard-hw2`.

## Model and data

The training script uses a fixed 80/20 stratified split with seed 42 and reports accuracy, spam precision, recall, and F1 on held-out messages. The model stores token counts in a small JSON file and runs with no third-party Python packages. A local copy of the corpus can be placed at `data/SMSSpamCollection`; otherwise the script reads the bundled zip archive.

Training corpus: SMS Spam Collection, by Tiago Almeida and Jose Hidalgo, [UCI Machine Learning Repository](https://doi.org/10.24432/C5CC84). The corpus is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); attribution is included in `data/README.txt`.

The corpus contains English SMS messages. Results for other languages may be unreliable. The score is a model estimate, not a guarantee or a substitute for checking suspicious links yourself.
