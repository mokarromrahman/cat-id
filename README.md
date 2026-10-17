# cat-id

Identifies Litten vs Shinx from a photo and posts the result to Discord.

## 1. Prepare data (on the server)
    data/Litten/*.jpg
    data/Shinx/*.jpg
    data/neither/*.jpg    # empty litterbox, people, other animals, blurry shots

Fast way to sort 1700 photos: put them all in `inbox/`, start the service, and
tap through `http://SERVER:8000/label` on your phone. Or bootstrap: sort ~50 of
each cat by hand, train, then let the model pre-sort the rest into the inbox.

## 2. Train (one-off, CPU is fine: minutes for 1700 images)
    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    python train.py

## 3. Run
    export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    export API_KEY=choose-a-secret
    docker compose up -d --build

Check: `curl http://SERVER:8000/health`
Test:  `curl -F file=@cat.jpg -F key=$API_KEY http://SERVER:8000/identify`

## 4. Capture (Raspberry Pi)
Install an "IP Webcam" style app on the S20 FE (serves a still at
`http://PHONE_IP:8080/photoaf.jpg`), give the phone a fixed IP, and run
`pi_trigger.py` with PHONE_SNAPSHOT, SERVER and API_KEY set.

## 5. Improve over time
Every capture is saved to `inbox/` with the guess in its name. Label the misses at
/label, then press "Retrain model now".

## TODO:
1. Raspberry pi
    - connect HC-SR501 and trigger on movement 
        - https://www.youtube.com/watch?v=P6mPoKdZ014
    - connect phone and figure out how to take photos and extract from the phone to the pi
    - send photos to the server
2. Server
    - train model
    - get discord webhook
    - create api key (jwt?)
        - does this key need to be saved in local .env file?
        - does the pi need one too?
3. Analytics
    - time and day analytics 
    - grafana dashboard for events?
    - discord or email alerts when cats haven't gone in {x} amount of hours?
    - what would vets care about seeing?
    - alerts for when the litterbox is cleaned?
        - alerts for when the litterbox hasn't been cleaned for {x} number of days?
    