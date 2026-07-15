layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uSegments;
uniform float uRotation;
uniform float uZoom;

void main()
{
    vec2 uv = vUV.st;
    vec2 p = (uv - 0.5) / max(uZoom, 0.001);
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    p.x *= aspect;
    float radius = length(p);
    float angle = atan(p.y, p.x) + uRotation;
    float wedge = 6.2831853 / max(2.0, floor(uSegments + 0.5));
    angle = abs(mod(angle + 0.5 * wedge, wedge) - 0.5 * wedge);
    vec2 folded = radius * vec2(cos(angle), sin(angle));
    folded.x /= aspect;
    vec2 effectUV = folded + 0.5;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], effectUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
