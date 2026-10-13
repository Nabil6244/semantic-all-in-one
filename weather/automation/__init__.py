"""Forecast automation (phase 2): the app writes the day's forecast by itself from the data; the user only records it.

    coverage   the 20 largest US metros (weather/data/metros.json) and the cities Weather can name
    fetch      one snapshot of every covered city plus the national alerts (coverage.json)
    story      the day's lead, by fixed rules, with "why this story" in plain words
    script     the script to read aloud, written from the snapshot (every number from the data)
    plan       beats.csv + weather_layers.csv from the snapshot, the story and the script
    prep       fetch -> story -> script -> plan -> resolved.json, written into a project folder all at once
    changes    what changed in the data since the prep, and which script lines say it
    schedule   the daily 5:30 AM Central prep as an OS task (text only until the user switches it on) and the catch-up rule

Run it: python -m weather.automation prep --project DIR --contact EMAIL_OR_URL"""
