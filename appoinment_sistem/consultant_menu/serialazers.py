from rest_framework import serializers
from consultant_menu.models import Consultant


class ConsultantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultant
        fields = ['id', 'first_name', 'last_name', 'middle_name', 'email', 'phone', 'created_at', 'updated_at',
                  'category_of_specialist']

