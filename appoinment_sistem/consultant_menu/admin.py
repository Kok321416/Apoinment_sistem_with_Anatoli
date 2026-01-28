from django.contrib import admin
from .models import Consultant, Category
admin.site.site_header = "Admin Panel"
admin.site.register(Consultant, admin.ModelAdmin)
admin.site.register(Category, admin.ModelAdmin)
