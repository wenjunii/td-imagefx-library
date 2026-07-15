layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uProgress;
uniform float uSoftness;
uniform float uCenterX;
uniform float uCenterY;
uniform float uReverse;

float aspectDistance(vec2 point, vec2 center, float aspect)
{
    vec2 delta = point - center;
    delta.x *= aspect;
    return length(delta);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 imageA = texture(sTD2DInputs[0], uv);
    vec4 imageB = texture(sTD2DInputs[1], uv);

    vec2 center = vec2(uCenterX, uCenterY);
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    float maximumDistance = max(
        max(aspectDistance(vec2(0.0, 0.0), center, aspect), aspectDistance(vec2(1.0, 0.0), center, aspect)),
        max(aspectDistance(vec2(0.0, 1.0), center, aspect), aspectDistance(vec2(1.0, 1.0), center, aspect))
    );
    float coordinate = aspectDistance(uv, center, aspect) / max(maximumDistance, 0.0001);
    coordinate = mix(coordinate, 1.0 - coordinate, step(0.5, uReverse));
    float progress = clamp(uProgress, 0.0, 1.0);
    float softness = max(uSoftness, 0.0001);
    float reveal = 1.0 - smoothstep(progress - softness, progress + softness, coordinate);
    reveal = progress <= 0.0 ? 0.0 : (progress >= 1.0 ? 1.0 : reveal);

    vec4 effect = mix(imageA, imageB, reveal);
    fragColor = TDOutputSwizzle(mix(imageA, effect, clamp(uMix, 0.0, 1.0)));
}
