from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0008_alter_order_checkout_url_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_deleted",
            field=models.BooleanField(default=False, verbose_name="已删除"),
        ),
    ]
