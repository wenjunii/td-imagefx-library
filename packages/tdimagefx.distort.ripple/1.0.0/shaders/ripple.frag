layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uFrequency;
uniform float uSpeed;
uniform float uDecay;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 center = vec2(uCenterX, uCenterY);
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    vec2 p = uv - center;
    p.x *= aspect;

    float distanceFromCenter = length(p);
    vec2 direction = distanceFromCenter > 0.000001 ? p / distanceFromCenter : vec2(0.0);
    float phase = distanceFromCenter * max(uFrequency, 0.001) * 6.28318530718 - uTime * uSpeed * 6.28318530718;
    float displacement = sin(phase) * uAmount * exp(-distanceFromCenter * max(uDecay, 0.0));
    vec2 sampleOffset = p + direction * displacement;
    sampleOffset.x /= aspect;
    vec2 sampleUV = clamp(center + sampleOffset, vec2(0.0), vec2(1.0));

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], sampleUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
