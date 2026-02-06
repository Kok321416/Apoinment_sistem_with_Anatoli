# Generated on server by makemigrations; added to repo so deploy keeps migration state.
# Consultant existed in bookings.0001_initial but was removed from models (main site uses consultant_menu.Consultant).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0006_sync_model_state"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Consultant",
        ),
    ]
