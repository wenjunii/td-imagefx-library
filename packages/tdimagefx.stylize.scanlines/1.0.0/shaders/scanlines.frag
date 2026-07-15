layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uDensity;
uniform float uStrength;
uniform float uSpeed;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float phase = uv.y * max(uDensity, 1.0) + uTime * uSpeed * 12.0;
    float scanline = 0.5 + 0.5 * sin(phase * 3.14159265);
    float attenuation = mix(1.0 - clamp(uStrength, 0.0, 1.0), 1.0, scanline);
    float grille = mod(floor(uv.x * uTD2DInfos[0].res.z), 3.0);
    vec3 mask = grille < 1.0 ? vec3(1.0, 0.94, 0.94) : (grille < 2.0 ? vec3(0.94, 1.0, 0.94) : vec3(0.94, 0.94, 1.0));
    vec4 effect = vec4(source.rgb * attenuation * mask, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
