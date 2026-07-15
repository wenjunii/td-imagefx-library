layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uProgress;
uniform float uSoftness;
uniform float uAngle;
uniform float uReverse;

void main()
{
    vec2 uv = vUV.st;
    vec4 imageA = texture(sTD2DInputs[0], uv);
    vec4 imageB = texture(sTD2DInputs[1], uv);

    vec2 direction = vec2(cos(uAngle), sin(uAngle));
    float extent = max(0.5 * (abs(direction.x) + abs(direction.y)), 0.0001);
    float coordinate = dot(uv - 0.5, direction) / (2.0 * extent) + 0.5;
    coordinate = mix(coordinate, 1.0 - coordinate, step(0.5, uReverse));
    float progress = clamp(uProgress, 0.0, 1.0);
    float softness = max(uSoftness, 0.0001);
    float reveal = 1.0 - smoothstep(progress - softness, progress + softness, coordinate);
    reveal = progress <= 0.0 ? 0.0 : (progress >= 1.0 ? 1.0 : reveal);

    vec4 effect = mix(imageA, imageB, reveal);
    fragColor = TDOutputSwizzle(mix(imageA, effect, clamp(uMix, 0.0, 1.0)));
}
