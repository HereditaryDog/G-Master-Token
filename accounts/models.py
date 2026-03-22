from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField("邮箱地址", unique=True)
    display_name = models.CharField("显示名称", max_length=80, blank=True)
    phone = models.CharField("联系电话", max_length=32, blank=True)
    is_merchant = models.BooleanField("商家账号", default=False)
    email_verified = models.BooleanField("邮箱已验证", default=False)
    email_verified_at = models.DateTimeField("邮箱验证时间", null=True, blank=True)

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.username
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.username


class EmailVerificationCode(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = "signup", "注册"

    email = models.EmailField("邮箱地址")
    purpose = models.CharField("用途", max_length=20, choices=Purpose.choices)
    code = models.CharField("验证码", max_length=6)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    expires_at = models.DateTimeField("过期时间")
    consumed_at = models.DateTimeField("使用时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "邮箱验证码"
        verbose_name_plural = "邮箱验证码"

    def mark_consumed(self):
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at"])

    @property
    def is_valid(self):
        now = timezone.now()
        return self.consumed_at is None and self.expires_at >= now
