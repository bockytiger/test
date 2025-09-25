# -*- coding: utf-8 -*-
"""
わり算シューティング
- pygameで作るシンプルな学習ゲーム
- 難易度3段階（初級・中級・上級）
- マウス操作で宇宙船を移動、クリックでビーム発射
- 4つの選択肢（隕石）が上から落ちてくる。正解の隕石を撃つと得点。
- 20問正解でそのレベルクリア。クリア後に次の難易度へ進める。
- 画像は外部アセットを使わず、pygameの描画で作成（宇宙船・隕石）
- 進捗バー、爆発エフェクト、星空の演出を含む

使い方:
$ pip install pygame
$ python warizan_shooting.py

"""

import pygame
import random
import math
import sys
from collections import deque

pygame.init()
WIDTH, HEIGHT = 900, 650
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("わり算シューティング")
clock = pygame.time.Clock()
FONT = pygame.font.SysFont("meiryo", 22)
BIGFONT = pygame.font.SysFont("meiryo", 40)

# --- 設定 ---
TARGET_CORRECT = 20
FALL_SPEED_MIN = 60   # px/sec
FALL_SPEED_MAX = 140

# --- ユーティリティ ---
def clamp(v, a, b):
    return max(a, min(b, v))

# --- 画像（プログラム生成） ---
def make_spaceship_surface(size=80):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    w, h = size, size
    # 本体
    pygame.draw.polygon(s, (200, 30, 30), [(w*0.5, h*0.05), (w*0.9, h*0.6), (w*0.5,h*0.9), (w*0.1,h*0.6)])
    # ウィンドウ
    pygame.draw.ellipse(s, (200, 220, 255), (w*0.35, h*0.25, w*0.3, h*0.2))
    pygame.draw.ellipse(s, (80, 120, 200), (w*0.37, h*0.28, w*0.26, h*0.14))
    # スラスター
    pygame.draw.polygon(s, (255,160,0), [(w*0.45,h*0.85),(w*0.55,h*0.85),(w*0.5,h*1.05)])
    return s

def make_meteor_surface(radius=36):
    size = radius*2
    s = pygame.Surface((size,size), pygame.SRCALPHA)
    # 本体
    base = (120, 80, 50)
    pygame.draw.circle(s, base, (radius,radius), radius)
    # クレーター風
    for _ in range(4):
        r = random.randint(6, radius//2)
        x = random.randint(radius//4, radius + radius//2)
        y = random.randint(radius//4, radius + radius//2)
        c = (90, 60, 40)
        pygame.draw.circle(s, c, (x,y), r)
    # ハイライト
    pygame.draw.circle(s, (180,130,80), (int(radius*0.6), int(radius*0.5)), int(radius*0.3), 1)
    return s

SPACESHIP_IMG = make_spaceship_surface(84)
METEOR_IMG = make_meteor_surface(38)

# --- パーティクル（爆発） ---
class ExplosionParticle:
    def __init__(self, pos):
        self.x, self.y = pos
        ang = random.random() * math.tau
        speed = random.uniform(80, 260)
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.life = random.uniform(0.5, 1.0)
        self.age = 0
        self.size = random.uniform(2,6)

    def update(self, dt):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surf):
        t = clamp(1 - self.age / self.life, 0, 1)
        if t <= 0: return
        alpha = int(255 * t)
        color = (255, 180, 50)
        r = int(self.size * (1+t))
        s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(s, color + (alpha,), (r,r), r)
        surf.blit(s, (self.x-r, self.y-r))

# --- 隕石（選択肢） ---
class Meteor:
    def __init__(self, x, y, text, speed):
        self.x = x
        self.y = y
        self.text = str(text)
        self.speed = speed
        self.surface = METEOR_IMG
        self.rect = self.surface.get_rect(center=(self.x, self.y))
        self.hit = False

    def update(self, dt):
        self.y += self.speed * dt
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        surf.blit(self.surface, self.rect.topleft)
        # テキスト
        txt = FONT.render(self.text, True, (255,255,255))
        tw, th = txt.get_size()
        surf.blit(txt, (self.x - tw//2, self.y - th//2))

# --- 問題生成 ---
class QuestionGenerator:
    def __init__(self, difficulty):
        self.set_difficulty(difficulty)

    def set_difficulty(self, difficulty):
        self.difficulty = difficulty
        if difficulty == 0:  # 初級
            self.divisors = list(range(1,6))  # 1~5段
            self.max_dividend = 20
        elif difficulty == 1:  # 中級
            self.divisors = list(range(6,10))  # 6~9段
            self.max_dividend = 60
        else:  # 上級
            self.divisors = list(range(1,10))
            self.max_dividend = 81

    def next_question(self):
        # 作り方: divisor (1-9) と quotient (1-9) を使って dividend を生成
        divisor = random.choice(self.divisors)
        # quotient を乱数で。dividend が制約内に収まるよう繰り返す
        for _ in range(200):
            quotient = random.randint(1, 12)
            dividend = divisor * quotient
            if 1 <= dividend <= self.max_dividend:
                return dividend, divisor, quotient
        # フォールバック
        quotient = 1
        dividend = divisor * quotient
        return dividend, divisor, quotient

# --- ゲーム本体 ---
class Game:
    def __init__(self):
        self.state = 'menu'  # menu, playing, level_clear
        self.difficulty = 0
        self.qgen = QuestionGenerator(self.difficulty)
        self.reset_play()
        self.particles = []
        self.explosions = []

    def reset_play(self):
        self.correct_count = 0
        self.total_attempts = 0
        self.current_question = None
        self.meteors = []
        self.ship_x = WIDTH//2
        self.ship_y = HEIGHT - 80
        self.beam = None
        self.beam_speed = 900
        self.spawn_timer = 0
        self.question_in_progress = False
        self.make_new_question()

    def make_new_question(self):
        self.current_question = self.qgen.next_question()
        dividend, divisor, quotient = self.current_question
        # 正解とダミーを作る
        answers = [quotient]
        while len(answers) < 4:
            # 近い値やランダム値を混ぜる
            candidate = quotient + random.choice([-3,-2,-1,1,2,3,4])
            if candidate < 1: candidate = random.randint(1, max(3, quotient+3))
            if candidate not in answers:
                answers.append(candidate)
        random.shuffle(answers)
        # 隕石配置（左右幅に均等）
        self.meteors = []
        margin = 70
        lane_w = (WIDTH - margin*2) / 4
        for i, a in enumerate(answers):
            x = int(margin + lane_w/2 + i*lane_w + random.uniform(-20,20))
            y = random.randint(-200, -60)
            speed = random.uniform(FALL_SPEED_MIN, FALL_SPEED_MAX)
            self.meteors.append(Meteor(x, y, a, speed))
        self.question_in_progress = True

    def fire_beam(self):
        # ビームは発射位置と方向（上向き）
        bx = self.ship_x
        by = self.ship_y - 34
        self.beam = [bx, by]

    def update(self, dt):
        # パーティクル更新
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.age < p.life]

        if self.state == 'playing':
            # ビーム移動
            if self.beam:
                self.beam[1] -= self.beam_speed * dt
            # 隕石更新
            for m in self.meteors:
                m.update(dt)
            # 衝突判定
            if self.beam:
                br = pygame.Rect(self.beam[0]-3, self.beam[1]-6, 6, 12)
                for m in list(self.meteors):
                    if m.rect.colliderect(br):
                        # ヒット
                        self.on_meteor_hit(m)
                        self.beam = None
                        break
                if self.beam and self.beam[1] < -40:
                    self.beam = None

            # 隕石が画面下に行った場合は問を進めて次へ
            for m in list(self.meteors):
                if m.y > HEIGHT + 60:
                    # ミス: 問題は不正解扱い（正解が落ちた場合も含む）
                    # 次の問題へ
                    self.meteors.remove(m)
                    # もし正解が画面外に行ったら次問題を出す
                    if not self.meteors:
                        self.total_attempts += 1
                        self.make_new_question()

            # レベルクリア判定
            if self.correct_count >= TARGET_CORRECT:
                self.state = 'level_clear'

        # menu and level_clear states do not need many updates

    def on_meteor_hit(self, meteor):
        # 正誤判定
        dividend, divisor, quotient = self.current_question
        hit_value = int(meteor.text)
        correct = (hit_value == quotient)
        self.total_attempts += 1
        if correct:
            self.correct_count += 1
            # 爆発エフェクトを作る
            for _ in range(30):
                self.particles.append(ExplosionParticle((meteor.x, meteor.y)))
        else:
            # 小さめの爆発
            for _ in range(12):
                self.particles.append(ExplosionParticle((meteor.x, meteor.y)))
        # 問題クリアまたは失敗のあと、次問へ
        # 全隕石をフェードアウト／削除
        self.meteors.clear()
        # 少し遅延して次の問題を出すためにspawn_timerを使う
        pygame.time.set_timer(pygame.USEREVENT+1, 450)

    def draw_background(self, surf):
        surf.fill((6, 10, 25))
        # 星を描く
        for i in range(80):
            x = (i * 97) % WIDTH
            y = (i * 61) % HEIGHT
            r = (i*13)%3 + 1
            pygame.draw.circle(surf, (220,220,255), (x, y), r)
        # ふんわりな星雲
        pygame.draw.circle(surf, (20,30,80,30), (WIDTH//3, HEIGHT//4), 180)
        pygame.draw.circle(surf, (30,20,60,30), (WIDTH*2//3, HEIGHT//3), 140)

    def draw_ui(self, surf):
        # 現在の問題を表示
        if self.current_question:
            dividend, divisor, quotient = self.current_question
            qtxt = f"{dividend} ÷ {divisor} = ?"
            txt = BIGFONT.render(qtxt, True, (255,255,200))
            surf.blit(txt, (20, 18))
        # 進捗バー
        bar_x, bar_y, bar_w, bar_h = 20, 80, 360, 26
        pygame.draw.rect(surf, (80,80,80), (bar_x, bar_y, bar_w, bar_h), border_radius=8)
        fill_w = int(bar_w * (self.correct_count / TARGET_CORRECT))
        pygame.draw.rect(surf, (50,200,120), (bar_x, bar_y, fill_w, bar_h), border_radius=8)
        pct = f"{self.correct_count}/{TARGET_CORRECT} 正解"
        surf.blit(FONT.render(pct, True, (255,255,255)), (bar_x + bar_w + 12, bar_y+3))
        # 難易度表示
        diffs = ["初級", "中級", "上級"]
        surf.blit(FONT.render(f"難易度: {diffs[self.difficulty]}", True, (220,220,220)), (20, 118))

        # 得点・試行回数
        surf.blit(FONT.render(f"試行: {self.total_attempts}", True, (200,200,200)), (20, 148))

    def draw(self, surf):
        self.draw_background(surf)
        if self.state == 'menu':
            self.draw_menu(surf)
        elif self.state == 'playing':
            # 隕石
            for m in self.meteors:
                m.draw(surf)
            # ビーム
            if self.beam:
                pygame.draw.rect(surf, (255,220,80), (self.beam[0]-3, self.beam[1]-14, 6, 28))
            # 宇宙船
            ship_rect = SPACESHIP_IMG.get_rect(center=(self.ship_x, self.ship_y))
            surf.blit(SPACESHIP_IMG, ship_rect.topleft)
            # パーティクル
            for p in self.particles:
                p.draw(surf)
            # UI
            self.draw_ui(surf)
        elif self.state == 'level_clear':
            self.draw_background(surf)
            msg = BIGFONT.render("レベルクリア！", True, (255, 230, 160))
            surf.blit(msg, (WIDTH//2 - msg.get_width()//2, HEIGHT//2 - 100))
            sub = FONT.render("次の難易度に進むか、同じレベルをもう一度プレイしてください。", True, (220,220,220))
            surf.blit(sub, (WIDTH//2 - sub.get_width()//2, HEIGHT//2 - 40))
            # 簡易ボタン描画（次へ / リトライ / メニュー）
            self.draw_buttons(surf)

    def draw_menu(self, surf):
        title = BIGFONT.render("わり算シューティング", True, (255,240,200))
        surf.blit(title, (WIDTH//2 - title.get_width()//2, 70))
        desc_lines = [
            "マウスで宇宙船を操作し、クリックでビームを発射します。",
            "正しい答えの隕石を撃って20問正解をめざそう！",
            "爆発やお祝いのエフェクトで楽しく学べます。"
        ]
        for i, line in enumerate(desc_lines):
            t = FONT.render(line, True, (210,210,210))
            surf.blit(t, (WIDTH//2 - t.get_width()//2, 180 + i*28))
        # 難易度ボタン
        self.draw_buttons(surf)

    def draw_buttons(self, surf):
        # Draw difficulty/select buttons and next/retry
        btns = []
        if self.state == 'menu':
            labels = ["初級（1-5段）", "中級（6-9段）", "上級（全段）"]
            for i, lab in enumerate(labels):
                x = WIDTH//2 - 220 + i*220
                y = 320
                w, h = 200, 48
                pygame.draw.rect(surf, (40,60,90), (x,y,w,h), border_radius=10)
                surf.blit(FONT.render(lab, True, (240,240,240)), (x+14, y+12))
                btns.append(((x,y,w,h), ('start', i)))
        elif self.state == 'level_clear':
            # next, retry, menu
            labels = [("次の難易度へ", (WIDTH//2 - 200, HEIGHT//2 + 20, 160, 50), ('next', None)),
                      ("もう一度やる", (WIDTH//2 - 20, HEIGHT//2 + 20, 160, 50), ('retry', None)),
                      ("メニューへ戻る", (WIDTH//2 + 160, HEIGHT//2 + 20, 160, 50), ('menu', None))]
            for lab, rect, tag in labels:
                x,y,w,h = rect
                pygame.draw.rect(surf, (50,90,70), (x,y,w,h), border_radius=10)
                surf.blit(FONT.render(lab, True, (240,240,240)), (x+12,y+14))
                btns.append(((x,y,w,h), tag))
        # store current buttons for click handling
        self._buttons = btns

    def handle_mouse(self, pos, buttons):
        mx, my = pos
        if self.state == 'menu':
            # highlight difficulty buttons is optional
            pass
        elif self.state == 'playing':
            # ship follow mouse x
            self.ship_x = clamp(mx, 40, WIDTH-40)
        elif self.state == 'level_clear':
            pass

    def handle_click(self, pos, button):
        mx,my = pos
        if self.state == 'menu':
            # check difficulty buttons
            # Recreate same areas as draw_buttons
            for i in range(3):
                x = WIDTH//2 - 220 + i*220
                y = 320
                w, h = 200, 48
                r = pygame.Rect(x,y,w,h)
                if r.collidepoint(pos):
                    self.difficulty = i
                    self.qgen.set_difficulty(i)
                    self.reset_play()
                    self.state = 'playing'
                    return
        elif self.state == 'playing':
            # 発射
            self.fire_beam()
        elif self.state == 'level_clear':
            # check buttons
            if hasattr(self, '_buttons'):
                for rect, tag in self._buttons:
                    x,y,w,h = rect
                    r = pygame.Rect(x,y,w,h)
                    if r.collidepoint(pos):
                        action = tag[0]
                        if action == 'next':
                            # 次の難易度へ（上限は上級）
                            if self.difficulty < 2:
                                self.difficulty += 1
                                self.qgen.set_difficulty(self.difficulty)
                            self.reset_play()
                            self.state = 'playing'
                        elif action == 'retry':
                            self.qgen.set_difficulty(self.difficulty)
                            self.reset_play()
                            self.state = 'playing'
                        elif action == 'menu':
                            self.state = 'menu'
                        return


# --- メインループ ---

game = Game()

running = True
# カーソル追従を有効
pygame.mouse.set_visible(True)

while running:
    dt = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEMOTION:
            mx,my = event.pos
            if game.state == 'playing':
                game.ship_x = clamp(mx, 40, WIDTH-40)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                game.handle_click(event.pos, event.button)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if game.state == 'playing':
                    game.state = 'menu'
                else:
                    running = False
        elif event.type == pygame.USEREVENT+1:
            # 次の問題を出すタイマーイベント
            pygame.time.set_timer(pygame.USEREVENT+1, 0)
            game.make_new_question()

    # Update
    game.update(dt)

    # Draw
    game.draw(screen)

    # 補助表示（残りの問題数）
    if game.state == 'playing':
        rem = TARGET_CORRECT - game.correct_count
        rem_txt = FONT.render(f"残り: {rem} 問", True, (240,240,240))
        screen.blit(rem_txt, (WIDTH - rem_txt.get_width() - 20, 20))

    pygame.display.flip()

pygame.quit()
sys.exit()
