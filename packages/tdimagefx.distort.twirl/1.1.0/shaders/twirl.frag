layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmount;
uniform float uRadius;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 center = vec2(uCenterX, uCenterY);
    vec2 delta = uv - center;
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    delta.x *= aspect;
    float radius = max(uRadius, 0.0001);
    float distanceFromCenter = length(delta);
    float falloff = clamp(1.0 - distanceFromCenter / radius, 0.0, 1.0);
    float angle = uAmount * falloff * falloff;
    float s = sin(angle);
    float c = cos(angle);
    delta = mat2(c, -s, s, c) * delta;
    delta.x /= aspect;
    vec2 warpedUV = center + delta;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], warpedUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
