from django.db import models

class Clients(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True, null=False, db_index=True)
    number = models.IntegerField()
    telegram_nickname = models.CharField(max_length=255, blank=True, null=False)
    who_your_consultant_name = models.ForeignKey(on_delete=models.PROTECT, to="Consultant", null=False)

    class Meta:
        db_table = "clients"

    def __str__(self):
        return f"{self.name} {self.number}"


class Consultant(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, null=False)
    last_name = models.CharField(max_length=255, blank=True, null=False)
    middle_name = models.CharField(max_length=255, blank=True, null=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)
    telegaram_nickname = models.CharField(max_length=255, blank=True, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category_of_specialist = models.ForeignKey(on_delete=models.PROTECT, to="Category")
    user = models.OneToOneField(Clients, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        db_table = "consultants"


class Category(models.Model):
    name_category = models.CharField(max_length=255, blank=True, null=False, db_index=True)



