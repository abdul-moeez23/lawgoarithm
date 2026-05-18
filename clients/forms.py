from django import forms
from .models import Case
import re

class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = [
            'title', 
            'category', 
            'subcategory', 
            'court_level', 
            'city', 
            'urgency', 
            'description'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Untitled Case'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'subcategory': forms.Select(attrs={'class': 'form-select'}),
            'court_level': forms.Select(attrs={'class': 'form-select'}),
            'city': forms.Select(attrs={'class': 'form-select'}),
            'urgency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Immediate action required'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 5, 
                'placeholder': 'Please describe: 1. The main legal issue, 2. Key events, and 3. Your desired outcome...'
            }),
        }

    def clean_description(self):
        description = self.cleaned_data.get('description')
        
        if not description:
            return description
            
        description = description.strip()

        # 1. Strip out all spaces, numbers, and symbols to leave ONLY the letters
        only_text = re.sub(r'[^a-zA-Z]', '', description)

        # 2. Check if there is enough actual text (e.g., at least 20 letters)
        if len(only_text) < 20:
            raise forms.ValidationError("Case description must contain real text (minimum 20 letters). Please avoid using too many symbols.")

        return description
