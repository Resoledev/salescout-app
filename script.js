// Auto-refresh every 30 minutes (1800000 ms) with cache-busting
setTimeout(function(){ window.location.href = '/?_=' + new Date().getTime(); }, 1800000);

// Stars animation
window.addEventListener('load', function() {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas || !canvas.getContext) {
        console.warn('Canvas element not found or unsupported');
        return;
    }
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const stars = [];
    const numStars = 200;
    for (let i = 0; i < numStars; i++) {
        stars.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            radius: Math.random() * 0.5 + 0.3,
            color: Math.random() > 0.8 ? '#10b981' : '#ffffff',
            speed: Math.random() * 0.5 + 0.1,
            direction: Math.random() * 2 * Math.PI,
            baseX: Math.random() * canvas.width,
            baseY: Math.random() * canvas.height
        });
    }

    let mouseX = canvas.width / 2;
    let mouseY = canvas.height / 2;

    canvas.addEventListener('mousemove', function(e) {
        mouseX = e.clientX;
        mouseY = e.clientY;
    });

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = false;
        stars.forEach(star => {
            const dx = mouseX - star.x;
            const dy = mouseY - star.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 150) {
                const angle = Math.atan2(dy, dx);
                star.x -= Math.cos(angle) * (150 - dist) / 50;
                star.y -= Math.sin(angle) * (150 - dist) / 50;
            } else {
                star.x += (star.baseX - star.x) * 0.01;
                star.y += (star.baseY - star.y) * 0.01;
            }

            star.radius = Math.random() * 0.5 + 0.3;
            ctx.globalAlpha = 0.7;
            ctx.beginPath();
            ctx.arc(star.x, star.y, star.radius, 0, 2 * Math.PI);
            ctx.fillStyle = star.color;
            ctx.fill();
            ctx.globalAlpha = 1;
        });
        requestAnimationFrame(animate);
    }

    animate();

    window.addEventListener('resize', function() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
});