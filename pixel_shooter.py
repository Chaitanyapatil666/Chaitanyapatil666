import os
import pygame, random, math, sys, numpy as np

# Ensure headless-friendly defaults if environment lacks devices
os.environ.setdefault("SDL_VIDEODRIVER", os.environ.get("SDL_VIDEODRIVER", ""))
os.environ.setdefault("SDL_AUDIODRIVER", os.environ.get("SDL_AUDIODRIVER", ""))

pygame.init()

# Audio safe init with fallback
AUDIO_ENABLED = True
try:
    pygame.mixer.init()
except Exception:
    AUDIO_ENABLED = False

WIDTH, HEIGHT = 1000, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pixel Shooter: Enhanced Edition")
clock = pygame.time.Clock()

BACKGROUND = (10, 10, 25)
PLAYER_COLOR = (0, 200, 100)
BULLET_COLORS = [(0, 255, 150), (220, 80, 60)]
ENEMY_COLORS = [(220, 80, 60), (220, 180, 60), (180, 60, 220), (200, 50, 50)]
POWERUP_COLORS = {"health": (255, 50, 50), "speed": (50, 200, 255), "rapid": (255, 200, 50),
                  "shield": (180, 100, 255), "freeze": (100, 200, 255), "explosive": (255, 150, 50)}
TEXT_COLOR = (230, 230, 230)
UI_BG = (30, 30, 50)
MENU_BG = (15, 15, 30)
BUTTON_COLOR = (50, 150, 200)
BUTTON_HOVER = (70, 170, 220)
BUTTON_TEXT = (240, 240, 240)
WORLD_WIDTH, WORLD_HEIGHT = 3000, 3000

stars = [[random.randint(0, WORLD_WIDTH), random.randint(0, WORLD_HEIGHT), 
          random.uniform(0.5, 2.5), random.randint(150, 255), 
          random.uniform(0.01, 0.05), 0] for _ in range(300)]

class _SilentSound:
    def play(self):
        pass

def _make_silent_sound():
    return _SilentSound()

def generate_tone(frequency, duration=0.1):
    if not AUDIO_ENABLED:
        return _make_silent_sound()
    try:
        sample_rate = 44100
        num_samples = int(duration * sample_rate)
        # Generate waveform
        t = np.arange(num_samples, dtype=np.float32)
        samples = 0.5 * np.sin(2 * np.pi * frequency * t / sample_rate)
        # Attack/decay envelope
        attack = min(int(0.05 * sample_rate), num_samples)
        decay = min(int(0.2 * sample_rate), num_samples)
        if attack > 0:
            samples[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
        if decay > 0:
            samples[-decay:] *= np.linspace(1.0, 0.0, decay, dtype=np.float32)
        samples_i16 = (samples * 32767).astype(np.int16)
        init_info = pygame.mixer.get_init()
        channels = 2 if (init_info and len(init_info) >= 3 and init_info[2] == 2) else 1
        if channels == 2:
            samples_i16 = np.column_stack((samples_i16, samples_i16))
        # For mono, pygame expects shape (n,), not (n,1)
        return pygame.sndarray.make_sound(samples_i16)
    except Exception:
        return _make_silent_sound()

# Re-init mixer with desired settings if audio is available
if AUDIO_ENABLED:
    try:
        pygame.mixer.quit()
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
    except Exception:
        AUDIO_ENABLED = False

SHOOT_SOUNDS = [generate_tone(440)]
HIT_SOUND = generate_tone(220)
POWERUP_SOUND = generate_tone(659)
EXPLOSION_SOUNDS = [generate_tone(110), generate_tone(147), generate_tone(220)]
FREEZE_SOUND = generate_tone(330)
MENU_SOUND = generate_tone(523)
LASER_SOUND = generate_tone(880, 0.5)
RELOAD_SOUND = generate_tone(220, 0.3)

font_large = pygame.font.SysFont(None, 64)
font_medium = pygame.font.SysFont(None, 36)
font_small = pygame.font.SysFont(None, 24)

class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.radius, self.speed, self.health, self.max_health = 20, 5, 100, 100
        self.shoot_cooldown, self.shoot_delay, self.bullet_power = 0, 10, 1
        self.direction, self.color = 0, PLAYER_COLOR
        self.score, self.invincible, self.regen_timer = 0, 0, 0
        self.powerups = {key: 0 for key in POWERUP_COLORS}
        self.shield_active = False
        self.weapons_unlocked = {"shotgun": False, "laser": False}
        self.active_weapon = "normal"
        self.laser_cooldown, self.laser_firing, self.laser_overheat, self.laser_overheat_max = 0, False, 0, 180
        self.shotgun_magazine, self.shotgun_max_magazine = 6, 6
        self.shotgun_reload_timer, self.shotgun_reload_time, self.shotgun_reloading = 0, 90, False
        self.space_pressed = False
        self.sprite = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(self.sprite, self.color, (20, 20), 20)
        pygame.draw.rect(self.sprite, (50, 50, 50), (20, 15, 25, 10))
        self.original_sprite = self.sprite.copy()
        
    def move(self, dx, dy):
        speed_mult = 1.5 if self.powerups["speed"] > 0 else 1.0
        self.x = max(self.radius, min(WORLD_WIDTH - self.radius, self.x + dx * self.speed * speed_mult))
        self.y = max(self.radius, min(WORLD_HEIGHT - self.radius, self.y + dy * self.speed * speed_mult))
            
    def update(self, mouse_pos):
        if self.shoot_cooldown > 0: self.shoot_cooldown -= 1
        if self.laser_cooldown > 0: self.laser_cooldown -= 1
        if self.laser_firing:
            self.laser_overheat = min(self.laser_overheat_max, self.laser_overheat + 3)
            if self.laser_overheat >= self.laser_overheat_max:
                self.laser_firing, self.laser_cooldown = False, 90
        elif self.laser_overheat > 0: self.laser_overheat = max(0, self.laser_overheat - 1)
        if self.shotgun_reloading:
            self.shotgun_reload_timer -= 1
            if self.shotgun_reload_timer <= 0:
                self.shotgun_magazine, self.shotgun_reloading = self.shotgun_max_magazine, False
            
        for powerup in self.powerups:
            if self.powerups[powerup] > 0:
                self.powerups[powerup] -= 1
                if powerup == "shield" and self.powerups[powerup] == 0: self.shield_active = False
        
        if self.invincible > 0: self.invincible -= 1
            
        if mouse_pos:
            dx = mouse_pos[0] - WIDTH // 2
            dy = mouse_pos[1] - HEIGHT // 2
            self.direction = math.atan2(dy, dx)
            
        self.regen_timer += 1
        if self.regen_timer >= 180 and self.health < self.max_health: self.heal(1)
    
    def shoot(self, bullets):
        if self.shoot_cooldown <= 0:
            delay = max(3, self.shoot_delay // 2) if self.powerups["rapid"] > 0 else self.shoot_delay
            self.shoot_cooldown = delay
            
            if self.active_weapon == "normal":
                bullets.append(Bullet(self.x, self.y, self.direction, 0, self.bullet_power, self.powerups["explosive"] > 0))
                SHOOT_SOUNDS[0].play()
                return True
            elif self.active_weapon == "shotgun" and self.weapons_unlocked["shotgun"]:
                if self.shotgun_magazine > 0 and not self.shotgun_reloading:
                    for angle_offset in [-30, -20, -10, 0, 10, 20, 30]:
                        angle = self.direction + math.radians(angle_offset)
                        bullets.append(Bullet(self.x, self.y, angle, 0, self.bullet_power, self.powerups["explosive"] > 0))
                    self.shotgun_magazine -= 1
                    SHOOT_SOUNDS[0].play()
                    return True
                elif self.shotgun_magazine == 0 and not self.shotgun_reloading: return self.reload_shotgun()
        return False
    
    def reload_shotgun(self):
        if not self.shotgun_reloading and self.shotgun_magazine < self.shotgun_max_magazine:
            self.shotgun_reloading, self.shotgun_reload_timer = True, self.shotgun_reload_time
            RELOAD_SOUND.play()
            return True
        return False
    
    def take_damage(self, amount):
        if self.invincible > 0: return False
        if self.shield_active:
            self.powerups["shield"] -= 20
            return False
            
        self.health -= amount
        self.invincible, self.regen_timer = 20, 0
        
        for _ in range(10):
            particles.append(Particle(
                self.x, self.y, random.uniform(0, 2*math.pi), random.uniform(1, 4), 
                random.randint(5, 12), (255, 150, 150), random.randint(15, 30)
            ))
        
        HIT_SOUND.play()
        return True
    
    def heal(self, amount): self.health = min(self.max_health, self.health + amount)
        
    def apply_powerup(self, powerup_type):
        POWERUP_SOUND.play()
        if powerup_type == "health": self.heal(30)
        elif powerup_type == "speed": self.powerups["speed"] = 600
        elif powerup_type == "rapid": self.powerups["rapid"] = 450
        elif powerup_type == "shield": 
            self.powerups["shield"], self.shield_active = 300, True
        elif powerup_type == "freeze": 
            self.powerups["freeze"] = 300
            FREEZE_SOUND.play()
        elif powerup_type == "explosive": self.powerups["explosive"] = 600
            
    def activate_laser(self, state):
        if state and not self.laser_firing and self.weapons_unlocked["laser"] and self.laser_cooldown <= 0:
            self.laser_firing = True
            LASER_SOUND.play()
            return True
        elif not state and self.laser_firing:
            self.laser_firing = False
            return True
        return False
            
    def draw(self, surface, camera_x, camera_y):
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        rotated_sprite = pygame.transform.rotate(self.original_sprite, -math.degrees(self.direction))
        surface.blit(rotated_sprite, rotated_sprite.get_rect(center=(int(screen_x), int(screen_y))))
        
        if self.shield_active:
            shield_radius = self.radius + 10
            shield_alpha = 150 + 100 * math.sin(pygame.time.get_ticks() / 100)
            shield_surf = pygame.Surface((shield_radius*2, shield_radius*2), pygame.SRCALPHA)
            pygame.draw.circle(shield_surf, (100, 200, 255, int(shield_alpha)), (shield_radius, shield_radius), shield_radius, 3)
            surface.blit(shield_surf, (int(screen_x - shield_radius), int(screen_y - shield_radius)))
            
        bar_width, bar_height = 50, 6
        bar_x, bar_y = int(screen_x - bar_width // 2), int(screen_y - self.radius - 15)
        pygame.draw.rect(surface, (100, 100, 100), (bar_x, bar_y, bar_width, bar_height))
        pygame.draw.rect(surface, (0, 255, 100), (bar_x, bar_y, int(bar_width * self.health / self.max_health), bar_height))
        
        if self.invincible > 0:
            alpha = 100 + 155 * abs(math.sin(pygame.time.get_ticks() / 50))
            flash_surf = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
            pygame.draw.circle(flash_surf, (255, 255, 255, int(alpha)), (self.radius, self.radius), self.radius)
            surface.blit(flash_surf, (int(screen_x - self.radius), int(screen_y - self.radius)))
            
        if self.powerups["freeze"] > 0:
            freeze_radius = self.radius + 15
            freeze_alpha = 100 + 155 * abs(math.sin(pygame.time.get_ticks() / 100))
            freeze_surf = pygame.Surface((freeze_radius*2, freeze_radius*2), pygame.SRCALPHA)
            pygame.draw.circle(freeze_surf, (100, 200, 255, int(freeze_alpha)), (freeze_radius, freeze_radius), freeze_radius, 3)
            surface.blit(freeze_surf, (int(screen_x - freeze_radius), int(screen_y - freeze_radius)))

class Bullet:
    def __init__(self, x, y, direction, player_id, power=1, explosive=False):
        self.x, self.y, self.direction = x, y, direction
        self.speed, self.radius, self.player_id, self.power = 10, 4, player_id, power
        self.lifetime, self.explosive = 90, explosive
        self.sprite = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        pygame.draw.circle(self.sprite, BULLET_COLORS[player_id], (self.radius, self.radius), self.radius)
        
    def update(self):
        self.x += math.cos(self.direction) * self.speed
        self.y += math.sin(self.direction) * self.speed
        self.lifetime -= 1
        return (self.x < -self.radius or self.x > WORLD_WIDTH + self.radius or
                self.y < -self.radius or self.y > WORLD_HEIGHT + self.radius or
                self.lifetime <= 0)
    
    def draw(self, surface, camera_x, camera_y):
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        
        if self.explosive:
            pygame.draw.circle(surface, (255, 150, 0), (int(screen_x), int(screen_y)), self.radius)
            for i in range(5):
                trail_x = screen_x - math.cos(self.direction) * i * 3
                trail_y = screen_y - math.sin(self.direction) * i * 3
                pygame.draw.circle(surface, (255, 200, 50), (int(trail_x), int(trail_y)), max(1, self.radius - i))
        else:
            surface.blit(self.sprite, (int(screen_x - self.radius), int(screen_y - self.radius)))
            for i in range(3):
                trail_x = screen_x - math.cos(self.direction) * i * 4
                trail_y = screen_y - math.sin(self.direction) * i * 4
                pygame.draw.circle(surface, self.sprite.get_at((0,0)), (int(trail_x), int(trail_y)), max(1, self.radius - i))
    
    def explode(self, enemies, particles, player):
        explosion_radius = 80
        for _ in range(30):
            particles.append(Particle(
                self.x, self.y, random.uniform(0, 2*math.pi), random.uniform(1, 7), 
                random.randint(5, 12), (255, random.randint(100, 180), 0), random.randint(30, 60)
            ))
        
        for enemy in enemies[:]:
            dx, dy = enemy.x - self.x, enemy.y - self.y
            distance = math.sqrt(dx*dx + dy*dy)
            if distance < explosion_radius:
                damage = int(50 * (1 - distance / explosion_radius))
                if enemy.take_damage(damage):
                    player.score += enemy.score_value
                    enemies.remove(enemy)
        
        EXPLOSION_SOUNDS[random.randint(0, 2)].play()

class Enemy:
    def __init__(self, x, y, enemy_type, wave_level):
        self.x, self.y, self.type, self.wave_level = x, y, enemy_type, wave_level
        self.speed_multiplier, self.is_frozen, self.immune_to_freeze = 1.0, False, False
        self.frozen_tint, self.original_color = (150, 220, 255), ENEMY_COLORS[enemy_type]
        self.frozen_particles_timer = 0
        
        if enemy_type == 0:  # Basic Shooter
            self.radius, self.base_speed = 16, 1.8 + wave_level * 0.04
            self.health = self.max_health = 30 + wave_level * 5
            self.shoot_delay, self.score_value = int(110 - min(70, wave_level * 1.8)), 10
        elif enemy_type == 1:  # Fast Charger
            self.radius, self.base_speed = 12, 3.0 + wave_level * 0.06
            self.health = self.max_health = 20 + wave_level * 3
            self.shoot_delay, self.score_value = 0, 15
        elif enemy_type == 2:  # Tank
            self.radius, self.base_speed = 24, 1.0 + wave_level * 0.025
            self.health = self.max_health = 80 + wave_level * 8
            self.shoot_delay, self.score_value = int(70 - min(45, wave_level * 1.3)), 30
        elif enemy_type == 3:  # Boss
            self.radius, self.base_speed = 50, 0.8 + wave_level * 0.02
            self.health = self.max_health = 500 + wave_level * 50
            self.shoot_delay, self.score_value = 60, 300
            self.attack_timer, self.attack_phase, self.phase_timer = 0, 0, 0
            self.shield = self.max_shield = 100
            self.immune_to_freeze = True
            
        self.shoot_cooldown = random.randint(0, self.shoot_delay) if self.shoot_delay > 0 else 0
        self.target_player, self.direction = None, random.uniform(0, 2*math.pi)
        self.collision_cooldown = 0
        self.sprite = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        pygame.draw.circle(self.sprite, self.original_color, (self.radius, self.radius), self.radius)
        pygame.draw.circle(self.sprite, (255, 50, 50), (self.radius, self.radius), self.radius//2)
        
    def update(self, player):
        self.target_player = player
        
        if player.powerups["freeze"] > 0 and not self.immune_to_freeze:
            self.speed_multiplier, self.is_frozen = 0.3, True
            self.color = tuple(min(255, (a + b) // 2) for a, b in zip(self.original_color, self.frozen_tint))
            self.frozen_particles_timer += 1
        else:
            self.speed_multiplier, self.is_frozen, self.color = 1.0, False, self.original_color
            
        if self.collision_cooldown > 0: self.collision_cooldown -= 1
            
        if self.target_player:
            dx, dy = self.target_player.x - self.x, self.target_player.y - self.y
            dist = max(0.1, math.sqrt(dx*dx + dy*dy))
            rand_angle = random.uniform(-0.5, 0.5)
            
            if self.type == 1: self.direction = math.atan2(dy, dx) + rand_angle * 0.1
            elif self.type == 3: self.direction = math.atan2(dy, dx) + rand_angle * 0.2
            else: self.direction = math.atan2(dy, dx) + rand_angle * 0.5
                
            self.x += math.cos(self.direction) * (self.base_speed * self.speed_multiplier)
            self.y += math.sin(self.direction) * (self.base_speed * self.speed_multiplier)
            
        if self.shoot_delay > 0 and not self.is_frozen: self.shoot_cooldown -= 1
            
        if self.type == 3:
            self.attack_timer += 1
            self.phase_timer += 1
            if self.phase_timer > 300:
                self.phase_timer, self.attack_phase = 0, (self.attack_phase + 1) % 3
            if self.health < self.max_health and self.attack_timer % 30 == 0: 
                self.shield = min(self.max_shield, self.shield + 1)
    
    def shoot(self, bullets):
        if self.type == 1 or self.is_frozen: return False
            
        if self.shoot_cooldown <= 0 and self.target_player:
            self.shoot_cooldown = self.shoot_delay
            
            if self.type == 3:
                if self.attack_phase == 0:
                    for i in range(12): bullets.append(Bullet(self.x, self.y, math.radians(i * 30), 1, 2))
                elif self.attack_phase == 1:
                    dx, dy = self.target_player.x - self.x, self.target_player.y - self.y
                    base_dir = math.atan2(dy, dx)
                    for angle_offset in [-30, -15, 0, 15, 30]:
                        bullets.append(Bullet(self.x, self.y, base_dir + math.radians(angle_offset), 1, 2))
                else:
                    dx, dy = self.target_player.x - self.x, self.target_player.y - self.y
                    dir = math.atan2(dy, dx)
                    for _ in range(3): bullets.append(HomingBullet(self.x, self.y, dir, 1, 2))
                SHOOT_SOUNDS[0].play()
                return True
            else:
                dx, dy = self.target_player.x - self.x, self.target_player.y - self.y
                direction = math.atan2(dy, dx) + random.uniform(-0.3, 0.3)
                bullets.append(Bullet(self.x, self.y, direction, 1, 1))
                SHOOT_SOUNDS[0].play()
                return True
        return False
    
    def take_damage(self, amount):
        if self.type == 3:
            if self.shield > 0:
                self.shield -= amount
                for _ in range(5):
                    particles.append(Particle(
                        self.x, self.y, random.uniform(0, 2*math.pi), random.uniform(1, 3), 
                        random.randint(4, 8), (100, 150, 255), random.randint(20, 40)
                    ))
                return False
            else: self.health -= amount
        else: self.health -= amount
            
        for _ in range(8):
            particles.append(Particle(
                self.x, self.y, random.uniform(0, 2*math.pi), random.uniform(1, 4), 
                random.randint(5, 10), (255, 200, 150), random.randint(15, 30)
            ))
        return self.health <= 0
    
    def draw(self, surface, camera_x, camera_y):
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        
        if self.is_frozen:
            if self.frozen_particles_timer % 10 == 0:
                for _ in range(3):
                    angle, distance = random.uniform(0, 2 * math.pi), random.uniform(0, self.radius * 1.5)
                    px, py = screen_x + math.cos(angle) * distance, screen_y + math.sin(angle) * distance
                    particles.append(Particle(
                        px + camera_x, py + camera_y, angle + math.pi, random.uniform(0.2, 0.8), 
                        random.randint(2, 4), (180, 220, 255), random.randint(30, 60)
                    ))
            
            ice_surf = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
            ice_alpha = 100 + 100 * abs(math.sin(pygame.time.get_ticks() / 100))
            pygame.draw.circle(ice_surf, (150, 220, 255, int(ice_alpha)), (self.radius, self.radius), self.radius)
            surface.blit(ice_surf, (int(screen_x - self.radius), int(screen_y - self.radius)))
        
        surface.blit(self.sprite, (int(screen_x - self.radius), int(screen_y - self.radius)))
        
        if self.type == 0:
            pygame.draw.circle(surface, (255, 50, 50), (int(screen_x), int(screen_y)), 6)
        elif self.type == 1:
            end_x = screen_x + math.cos(self.direction) * (self.radius + 5)
            end_y = screen_y + math.sin(self.direction) * (self.radius + 5)
            pygame.draw.line(surface, (255, 255, 150), (int(screen_x), int(screen_y)), (int(end_x), int(end_y)), 3)
        elif self.type == 2:
            pygame.draw.circle(surface, (100, 100, 150), (int(screen_x), int(screen_y)), self.radius, 3)
        elif self.type == 3:
            pygame.draw.circle(surface, (50, 0, 0), (int(screen_x), int(screen_y)), self.radius - 10)
            pygame.draw.line(surface, (0, 0, 0), (int(screen_x - 15), int(screen_y - 15)), (int(screen_x + 15), int(screen_y + 15)), 6)
            pygame.draw.line(surface, (0, 0, 0), (int(screen_x + 15), int(screen_y - 15)), (int(screen_x - 15), int(screen_y + 15)), 6)
            if self.shield > 0:
                bar_width, bar_height = 100, 8
                bar_x, bar_y = int(screen_x - bar_width // 2), int(screen_y - self.radius - 20)
                pygame.draw.rect(surface, (100, 100, 100), (bar_x, bar_y, bar_width, bar_height))
                pygame.draw.rect(surface, (100, 150, 255), (bar_x, bar_y, int(bar_width * self.shield / self.max_shield), bar_height))
        
        bar_width = 100 if self.type == 3 else 40
        bar_height = 5
        bar_x, bar_y = int(screen_x - bar_width // 2), int(screen_y - self.radius - 10)
        pygame.draw.rect(surface, (100, 100, 100), (bar_x, bar_y, bar_width, bar_height))
        pygame.draw.rect(surface, (255, 100, 100), (bar_x, bar_y, int(bar_width * self.health / self.max_health), bar_height))

class HomingBullet(Bullet):
    def __init__(self, x, y, direction, player_id, power=1):
        super().__init__(x, y, direction, player_id, power)
        self.speed, self.turn_speed, self.lifetime = 7, 0.05, 180
        self.trail = []
        
    def update(self):
        if self.player_id == 0:
            closest = min(enemies, key=lambda e: math.sqrt((e.x - self.x)**2 + (e.y - self.y)**2), default=None)
        else: closest = player
            
        if closest:
            dx, dy = closest.x - self.x, closest.y - self.y
            min_dist = math.sqrt(dx*dx + dy*dy)
            if min_dist < 500:
                target_dir = math.atan2(dy, dx)
                diff = (target_dir - self.direction + math.pi) % (2 * math.pi) - math.pi
                self.direction += min(max(diff, -self.turn_speed), self.turn_speed)
        
        self.x += math.cos(self.direction) * self.speed
        self.y += math.sin(self.direction) * self.speed
        self.lifetime -= 1
        self.trail.append((self.x, self.y))
        if len(self.trail) > 10: self.trail.pop(0)
        return (self.x < -self.radius or self.x > WORLD_WIDTH + self.radius or
                self.y < -self.radius or self.y > WORLD_HEIGHT + self.radius or
                self.lifetime <= 0)
    
    def draw(self, surface, camera_x, camera_y):
        for i, (trail_x, trail_y) in enumerate(self.trail):
            screen_x, screen_y = trail_x - camera_x, trail_y - camera_y
            alpha = int(255 * (i / len(self.trail))) if self.trail else 0
            size = int(self.radius * (i / len(self.trail))) if self.trail else 0
            # Draw trail on an alpha surface to respect per-pixel alpha
            if size > 0:
                temp = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
                pygame.draw.circle(temp, (255, 100, 200, alpha), (size, size), size)
                surface.blit(temp, (int(screen_x - size), int(screen_y - size)))
        
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        pygame.draw.circle(surface, (255, 100, 200), (int(screen_x), int(screen_y)), self.radius)

class Powerup:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.radius, self.lifetime, self.pulse_timer = 12, 600, 0
        self.type = random.choice(list(POWERUP_COLORS.keys()))
        self.color = POWERUP_COLORS[self.type]
        self.name = {
            "health": "Health Pack", "speed": "Speed Boost", "rapid": "Rapid Fire",
            "shield": "Energy Shield", "freeze": "Cryo Grenade", "explosive": "Explosive Rounds"
        }.get(self.type, "Powerup")
        self.sprite = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(self.sprite, self.color, (12, 12), 12)
        pygame.draw.circle(self.sprite, (255, 255, 255), (12, 12), 4)
        
    def update(self):
        self.lifetime -= 1
        self.pulse_timer = (self.pulse_timer + 1) % 60
        return self.lifetime <= 0
    
    def draw(self, surface, camera_x, camera_y):
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        pulse_size = 1 + 0.5 * math.sin(self.pulse_timer * 0.1)
        radius = int(self.radius * pulse_size)
        
        glow_surf = pygame.Surface((radius*4, radius*4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*self.color, 100), (radius*2, radius*2), radius*2)
        surface.blit(glow_surf, (int(screen_x - radius*2), int(screen_y - radius*2)))
        surface.blit(self.sprite, (int(screen_x - self.radius), int(screen_y - self.radius)))
        name_text = font_small.render(self.name, True, TEXT_COLOR)
        surface.blit(name_text, name_text.get_rect(center=(int(screen_x), int(screen_y - 20))))

class Particle:
    def __init__(self, x, y, angle, speed, radius, color, lifetime):
        self.x, self.y = x, y
        self.angle, self.speed, self.radius = angle, speed, radius
        self.color, self.lifetime, self.original_lifetime = color, lifetime, lifetime
        self.velocity_x = math.cos(angle) * speed
        self.velocity_y = math.sin(angle) * speed
        self.gravity = 0.1 if random.random() > 0.7 else 0
        
    def update(self):
        self.x += self.velocity_x
        self.y += self.velocity_y
        self.velocity_y += self.gravity
        self.lifetime -= 1
        self.radius = max(0.0, self.radius * 0.95)
        return self.lifetime <= 0
    
    def draw(self, surface, camera_x, camera_y):
        screen_x, screen_y = self.x - camera_x, self.y - camera_y
        size = max(1, int(self.radius * 2))
        temp_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        alpha = int(255 * self.lifetime / max(1, self.original_lifetime))
        center = size // 2
        pygame.draw.circle(temp_surf, (*self.color, alpha), (center, center), center)
        surface.blit(temp_surf, (int(screen_x - center), int(screen_y - center)))

class Button:
    def __init__(self, x, y, width, height, text, action):
        self.rect = pygame.Rect(x, y, width, height)
        self.text, self.action, self.hovered = text, action, False
        
    def draw(self, surface):
        color = BUTTON_HOVER if self.hovered else BUTTON_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, (100, 200, 255), self.rect, 3, border_radius=10)
        text_surf = font_medium.render(self.text, True, BUTTON_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))
        
    def check_hover(self, pos): self.hovered = self.rect.collidepoint(pos)
        
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hovered:
            MENU_SOUND.play()
            return self.action

def draw_weapon_icon(surface, x, y, weapon_type, active=False):
    size, color = 30, (100, 255, 100) if active else (150, 150, 150)
    if weapon_type == "normal":
        pygame.draw.circle(surface, color, (x, y), size//2)
        pygame.draw.circle(surface, (255, 255, 255), (x + 8, y), 6)
    elif weapon_type == "shotgun":
        pygame.draw.circle(surface, color, (x, y), size//2)
        for i in range(5):
            angle = math.radians(-30 + i * 15)
            end_x, end_y = x + math.cos(angle) * 15, y + math.sin(angle) * 15
            pygame.draw.line(surface, (255, 255, 255), (x, y), (int(end_x), int(end_y)), 3)
    elif weapon_type == "laser":
        pygame.draw.circle(surface, color, (x, y), size//2)
        pygame.draw.line(surface, (50, 200, 255), (x - 8, y), (x + 8, y), 4)
        pygame.draw.line(surface, (100, 250, 255), (x - 5, y), (x + 5, y), 2)

player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
bullets, enemies, powerups, particles = [], [], [], []
wave, enemies_to_spawn, spawn_timer = 1, 5, 0
game_over, game_won = False, False
wave_start_time, unlock_message_time = pygame.time.get_ticks(), 0
powerup_spawn_timer, boss_spawned_this_wave = 0, False
unlock_message = ""
MENU, PLAYING, GAME_OVER, GAME_WON = 0, 1, 2, 3
game_state = MENU
start_button = Button(WIDTH//2 - 100, HEIGHT//2, 200, 60, "Start Game", PLAYING)
quit_button = Button(WIDTH//2 - 100, HEIGHT//2 + 100, 200, 60, "Quit", "quit")

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
            
        if game_state == MENU:
            start_button.check_hover(pygame.mouse.get_pos())
            quit_button.check_hover(pygame.mouse.get_pos())
            
            action = start_button.handle_event(event) or quit_button.handle_event(event)
            if action == PLAYING:
                game_state = PLAYING
                player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
                bullets, enemies, powerups, particles = [], [], [], []
                wave, enemies_to_spawn, spawn_timer = 1, 5, 0
                game_over, game_won = False, False
                wave_start_time = pygame.time.get_ticks()
                unlock_message = ""
                unlock_message_time = 0
                powerup_spawn_timer = 0
                boss_spawned_this_wave = False
            elif action == "quit": running = False
                
        elif game_state == PLAYING:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: game_state = MENU
                elif event.key == pygame.K_1: player.active_weapon = "normal"
                elif event.key == pygame.K_2 and player.weapons_unlocked["shotgun"]: player.active_weapon = "shotgun"
                elif event.key == pygame.K_3 and player.weapons_unlocked["laser"]: player.active_weapon = "laser"
                elif event.key == pygame.K_r and player.active_weapon == "shotgun" and player.weapons_unlocked["shotgun"]: player.reload_shotgun()
                elif event.key == pygame.K_SPACE: player.space_pressed = True
            elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE: player.space_pressed = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if player.active_weapon == "laser" and player.weapons_unlocked["laser"]: player.activate_laser(True)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if player.active_weapon == "laser" and player.weapons_unlocked["laser"]: player.activate_laser(False)
        
        elif game_state in (GAME_OVER, GAME_WON):
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_r, pygame.K_ESCAPE): game_state = MENU
    
    mouse_pos = pygame.mouse.get_pos()
    
    if game_state == MENU:
        screen.fill(MENU_BG)
        screen.blit(font_large.render("PIXEL SHOOTER", True, (100, 200, 255)), (WIDTH//2 - 150, HEIGHT//4))
        screen.blit(font_medium.render("Enhanced Edition", True, (180, 220, 255)), (WIDTH//2 - 100, HEIGHT//4 + 70))
        
        instructions = [
            "CONTROLS:", "WASD - Move", "Mouse - Aim", "SPACE - Shoot (Hold)",
            "1, 2, 3 - Switch Weapons", "R - Reload Shotgun", 
            "Hold Mouse1 - Fire Laser", "ESC - Return to Menu"
        ]
        for i, line in enumerate(instructions):
            screen.blit(font_small.render(line, True, TEXT_COLOR), (WIDTH//2 - 150, HEIGHT//2 + 200 + i * 30))
        
        start_button.draw(screen)
        quit_button.draw(screen)
        pygame.display.flip()
        clock.tick(60)
        continue
    
    camera_x = max(0, min(WORLD_WIDTH - WIDTH, player.x - WIDTH // 2))
    camera_y = max(0, min(WORLD_HEIGHT - HEIGHT, player.y - HEIGHT // 2))
    
    if game_state == PLAYING and not (game_over or game_won):
        keys = pygame.key.get_pressed()
        dx = keys[pygame.K_d] - keys[pygame.K_a]
        dy = keys[pygame.K_s] - keys[pygame.K_w]
        player.move(dx, dy)
        player.update(mouse_pos)
        
        if player.space_pressed and player.active_weapon != "laser": player.shoot(bullets)
        
        if player.laser_firing and player.active_weapon == "laser" and player.weapons_unlocked["laser"]:
            laser_end_x = player.x + math.cos(player.direction) * 500
            laser_end_y = player.y + math.sin(player.direction) * 500
            
            for enemy in enemies[:]:
                px, py = enemy.x, enemy.y
                x1, y1, x2, y2 = player.x, player.y, laser_end_x, laser_end_y
                A, B, C, D = px - x1, py - y1, x2 - x1, y2 - y1
                dot, len_sq = A * C + B * D, C * C + D * D
                param = dot / len_sq if len_sq != 0 else -1
                if param < 0: xx, yy = x1, y1
                elif param > 1: xx, yy = x2, y2
                else: xx, yy = x1 + param * C, y1 + param * D
                
                distance = math.sqrt((px - xx)**2 + (py - yy)**2)
                if distance < enemy.radius:
                    if enemy.take_damage(5):
                        player.score += enemy.score_value
                        enemies.remove(enemy)
                        for _ in range(5):
                            particles.append(Particle(
                                xx, yy, random.uniform(0, 2*math.pi), random.uniform(0.5, 3), 
                                random.randint(4, 8), (100, 200, 255), random.randint(20, 40)
                            ))
            
            if random.random() < 0.8:
                dist = random.uniform(0, 500)
                px = player.x + math.cos(player.direction) * dist
                py = player.y + math.sin(player.direction) * dist
                particles.append(Particle(
                    px, py, random.uniform(0, 2*math.pi), random.uniform(0.5, 2), 
                    random.randint(2, 4), (50, 200, 255), random.randint(10, 20)
                ))
        
        for bullet in bullets[:]:
            if bullet.update():
                if bullet.explosive and bullet.player_id == 0: bullet.explode(enemies, particles, player)
                bullets.remove(bullet)
                continue
                
            if bullet.player_id == 0:
                for enemy in enemies[:]:
                    dx, dy = bullet.x - enemy.x, bullet.y - enemy.y
                    if math.sqrt(dx*dx + dy*dy) < bullet.radius + enemy.radius:
                        if enemy.take_damage(bullet.power * 15):
                            player.score += enemy.score_value
                            for _ in range(30):
                                particles.append(Particle(
                                    enemy.x, enemy.y, random.uniform(0, 2*math.pi), random.uniform(1, 8), 
                                    random.randint(8, 16), random.choice([(255, 100, 50), (255, 200, 50), (255, 50, 50)]), 
                                    random.randint(30, 60)
                                ))
                            if random.random() < 0.1: powerups.append(Powerup(enemy.x, enemy.y))
                            enemies.remove(enemy)
                            EXPLOSION_SOUNDS[random.randint(0, 2)].play()
                        if bullet in bullets: bullets.remove(bullet)
                        if bullet.explosive and bullet.player_id == 0: bullet.explode(enemies, particles, player)
                        break
            
            elif bullet.player_id == 1:
                dx, dy = bullet.x - player.x, bullet.y - player.y
                if math.sqrt(dx*dx + dy*dy) < bullet.radius + player.radius:
                    player.take_damage(8)
                    bullets.remove(bullet)
                    for _ in range(10):
                        particles.append(Particle(
                            bullet.x, bullet.y, random.uniform(0, 2*math.pi), random.uniform(1, 4), 
                            random.randint(3, 8), bullet.sprite.get_at((0,0)), random.randint(15, 30)
                        ))
                    break
        
        spawn_timer -= 1
        if spawn_timer <= 0 and enemies_to_spawn > 0:
            angle, distance = random.uniform(0, 2 * math.pi), random.uniform(400, 600)
            x = max(100, min(WORLD_WIDTH - 100, player.x + math.cos(angle) * distance))
            y = max(100, min(WORLD_HEIGHT - 100, player.y + math.sin(angle) * distance))
            
            if wave < 3: enemy_type = 0
            elif wave < 6: enemy_type = random.choices([0, 1], weights=[0.7, 0.3])[0]
            elif wave < 10: enemy_type = random.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0]
            else:
                if wave % 5 == 0 and not boss_spawned_this_wave:
                    enemy_type, boss_spawned_this_wave = 3, True
                else: enemy_type = random.choices([0, 1, 2], weights=[0.5, 0.3, 0.2])[0]
                
            enemies.append(Enemy(x, y, enemy_type, wave))
            if enemy_type != 3: enemies_to_spawn -= 1
            spawn_timer = max(15, 70 - wave * 2)
            
        for enemy in enemies:
            enemy.update(player)
            enemy.shoot(bullets)
            
            dx, dy = enemy.x - player.x, enemy.y - player.y
            distance = math.sqrt(dx*dx + dy*dy)
            min_distance = enemy.radius + player.radius + 2
            
            if distance < min_distance and enemy.collision_cooldown <= 0:
                push_x, push_y = (player.x - enemy.x) / distance, (player.y - enemy.y) / distance
                enemy.x -= push_x * 5
                enemy.y -= push_y * 5
                enemy.collision_cooldown = 20
                player.take_damage(10)
                for _ in range(15):
                    particles.append(Particle(
                        enemy.x, enemy.y, random.uniform(0, 2*math.pi), random.uniform(1, 4), 
                        random.randint(4, 8), (255, 150, 100), random.randint(20, 40)
                    ))
        
        for powerup in powerups[:]:
            if powerup.update(): powerups.remove(powerup)
            else:
                dx, dy = powerup.x - player.x, powerup.y - player.y
                if math.sqrt(dx*dx + dy*dy) < powerup.radius + player.radius:
                    player.apply_powerup(powerup.type)
                    powerups.remove(powerup)
                    for _ in range(30):
                        particles.append(Particle(
                            powerup.x, powerup.y, random.uniform(0, 2*math.pi), random.uniform(1, 4), 
                            random.randint(3, 7), powerup.color, random.randint(25, 45)
                        ))
                    break
        
        particles = [p for p in particles if not p.update()]
        
        if player.score >= 500 and not player.weapons_unlocked["shotgun"]:
            player.weapons_unlocked["shotgun"] = True
            unlock_message, unlock_message_time = "Shotgun Unlocked! (Press 2)", pygame.time.get_ticks()
        elif player.score >= 1500 and not player.weapons_unlocked["laser"]:
            player.weapons_unlocked["laser"] = True
            unlock_message, unlock_message_time = "Laser Unlocked! (Press 3)", pygame.time.get_ticks()
        
        powerup_spawn_timer -= 1
        if powerup_spawn_timer <= 0:
            angle, distance = random.uniform(0, 2 * math.pi), random.uniform(300, 500)
            x = max(100, min(WORLD_WIDTH - 100, player.x + math.cos(angle) * distance))
            y = max(100, min(WORLD_HEIGHT - 100, player.y + math.sin(angle) * distance))
            powerups.append(Powerup(x, y))
            powerup_spawn_timer = 1800
        
        if enemies_to_spawn == 0 and len(enemies) == 0:
            wave += 1
            enemies_to_spawn = min(50, 5 + wave * 3)
            spawn_timer, wave_start_time, boss_spawned_this_wave = 120, pygame.time.get_ticks(), False
            
        if player.health <= 0: game_over, game_state = True, GAME_OVER
        if wave > 20: game_won, game_state = True, GAME_WON
    
    screen.fill(BACKGROUND)
    
    for star in stars:
        x, y, size, base_brightness, twinkle_speed, phase = star
        phase += twinkle_speed
        brightness = max(0, min(255, base_brightness + 50 * math.sin(phase)))
        star[5] = phase
        screen_x, screen_y = x - camera_x, y - camera_y
        if 0 <= screen_x <= WIDTH and 0 <= screen_y <= HEIGHT:
            pygame.draw.circle(screen, (int(brightness), int(brightness), int(brightness)), 
                              (int(screen_x), int(screen_y)), max(1, int(size)))
    
    for particle in particles: particle.draw(screen, camera_x, camera_y)
    for powerup in powerups: powerup.draw(screen, camera_x, camera_y)
    for bullet in bullets: bullet.draw(screen, camera_x, camera_y)
    
    if player.laser_firing and player.active_weapon == "laser" and player.weapons_unlocked["laser"]:
        laser_end_x = player.x + math.cos(player.direction) * 500
        laser_end_y = player.y + math.sin(player.direction) * 500
        screen_x1, screen_y1 = player.x - camera_x, player.y - camera_y
        screen_x2, screen_y2 = laser_end_x - camera_x, laser_end_y - camera_y
        
        for i in range(3):
            width, glow_color = 5 - i, (50, 150+30*i, 255)
            pygame.draw.line(screen, glow_color, (int(screen_x1), int(screen_y1)), (int(screen_x2), int(screen_y2)), width)
        
        pygame.draw.circle(screen, (100, 220, 255), (int(screen_x2), int(screen_y2)), 15)
        pygame.draw.circle(screen, (150, 240, 255), (int(screen_x2), int(screen_y2)), 8)
    
    for enemy in enemies: enemy.draw(screen, camera_x, camera_y)
    player.draw(screen, camera_x, camera_y)
    
    ui_surface = pygame.Surface((WIDTH, 50), pygame.SRCALPHA)
    ui_surface.fill(UI_BG + (180,))
    screen.blit(ui_surface, (0, 0))
    pygame.draw.line(screen, (80, 80, 120), (0, 50), (WIDTH, 50), 2)
    
    screen.blit(font_medium.render(f"Wave: {wave}", True, TEXT_COLOR), (20, 10))
    screen.blit(font_medium.render(f"Score: {player.score}", True, TEXT_COLOR), (WIDTH//2 - 50, 10))
    screen.blit(font_small.render(f"Health: {player.health}", True, player.color), (WIDTH - 220, 15))
    screen.blit(font_small.render(f"Weapon: {player.active_weapon.capitalize()}", True, TEXT_COLOR), (WIDTH - 400, 15))
    
    draw_weapon_icon(screen, 70, 25, "normal", player.active_weapon == "normal")
    if player.weapons_unlocked["shotgun"]: draw_weapon_icon(screen, 120, 25, "shotgun", player.active_weapon == "shotgun")
    if player.weapons_unlocked["laser"]: draw_weapon_icon(screen, 170, 25, "laser", player.active_weapon == "laser")
    
    if player.weapons_unlocked["laser"]:
        bar_width, bar_height = 100, 8
        bar_x, bar_y = 200, 20
        pygame.draw.rect(screen, (80, 80, 100), (bar_x, bar_y, bar_width, bar_height))
        pygame.draw.rect(screen, (200, 200, 255), (bar_x, bar_y, int(bar_width * player.laser_overheat / player.laser_overheat_max), bar_height))
        pygame.draw.rect(screen, (100, 200, 255), (bar_x, bar_y, bar_width, bar_height), 2)
        screen.blit(font_small.render("LASER", True, (180, 220, 255)), (bar_x + bar_width + 5, bar_y - 3))
    
    if player.weapons_unlocked["shotgun"] and player.active_weapon == "shotgun":
        ammo_x, ammo_y = 220, 40
        screen.blit(font_small.render(f"{player.shotgun_magazine}/{player.shotgun_max_magazine}", True, TEXT_COLOR), (ammo_x, ammo_y))
        if player.shotgun_reloading:
            reload_width, reload_height = 80, 6
            reload_x, reload_y = ammo_x - 10, ammo_y + 20
            pygame.draw.rect(screen, (80, 80, 100), (reload_x, reload_y, reload_width, reload_height))
            progress = 1 - (player.shotgun_reload_timer / player.shotgun_reload_time)
            pygame.draw.rect(screen, (200, 200, 100), (reload_x, reload_y, int(reload_width * progress), reload_height))
            pygame.draw.rect(screen, (150, 150, 100), (reload_x, reload_y, reload_width, reload_height), 1)
    
    powerup_x = WIDTH - 600
    for j, powerup in enumerate(player.powerups):
        time_left = player.powerups[powerup]
        if time_left > 0:
            color = POWERUP_COLORS[powerup]
            pygame.draw.circle(screen, color, (powerup_x + j * 30, 25), 10)
            pygame.draw.rect(screen, (100, 100, 100), (powerup_x + j * 30 - 15, 35, 30, 5))
            pygame.draw.rect(screen, color, (powerup_x + j * 30 - 15, 35, int(30 * time_left / 600), 5))
    
    if pygame.time.get_ticks() - wave_start_time < 2000:
        wave_progress = (pygame.time.get_ticks() - wave_start_time) / 2000
        alpha = int(255 * (1 - abs(wave_progress - 0.5) * 2))
        wave_text = font_large.render(f"WAVE {wave}", True, (255, 200, 100))
        wave_text.set_alpha(alpha)
        wave_surface = pygame.Surface(wave_text.get_size(), pygame.SRCALPHA)
        wave_surface.blit(wave_text, (0, 0))
        screen.blit(wave_surface, (WIDTH//2 - wave_surface.get_width()//2, HEIGHT//2 - wave_surface.get_height()//2))
    
    if unlock_message and pygame.time.get_ticks() - unlock_message_time < 3000:
        screen.blit(font_medium.render(unlock_message, True, (100, 255, 200)), 
                     (WIDTH//2 - font_medium.size(unlock_message)[0]//2, HEIGHT - 100))
    
    if game_state == GAME_OVER or game_state == GAME_WON:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180) if game_state == GAME_OVER else (0, 30, 0, 180))
        screen.blit(overlay, (0, 0))
        title = "GAME OVER" if game_state == GAME_OVER else "VICTORY!"
        color = (255, 100, 100) if game_state == GAME_OVER else (100, 255, 150)
        title_surf = font_large.render(title, True, color)
        screen.blit(title_surf, (WIDTH//2 - title_surf.get_width()//2, HEIGHT//2 - 50))
        score_surf = font_medium.render(f"Final Score: {player.score}", True, TEXT_COLOR)
        screen.blit(score_surf, (WIDTH//2 - score_surf.get_width()//2, HEIGHT//2 + 20))
        restart_text = "Press R to Restart" if game_state == GAME_OVER else "Press R to Play Again"
        restart_surf = font_medium.render(restart_text, True, TEXT_COLOR)
        screen.blit(restart_surf, (WIDTH//2 - restart_surf.get_width()//2, HEIGHT//2 + 80))
      
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()